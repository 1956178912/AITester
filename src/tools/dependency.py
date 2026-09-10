"""
第三方依赖检测与隔离执行环境（venv）管理模块。

背景（P0/P1 环境问题）：
    本地执行模式直接在系统 Python 中运行 pytest：
    1. 被测代码 import 的第三方库缺失时测试直接失败，
       且无法区分"代码 bug"与"环境缺依赖"；
    2. 不同任务/项目的依赖互相冲突，import 污染系统环境。

本模块提供：
    - extract_imported_modules: 从源码提取 import 的顶层模块名
    - find_missing_modules:    判断哪些模块在本机环境不可用（区分 stdlib/第三方）
    - suggest_package_names:   模块名 → pip 包名映射（PIL→Pillow 等常见不一致）
    - create_venv:             创建带 --system-site-packages 的隔离 venv（带磁盘缓存）
    - install_packages:        在指定 venv 内 pip install（不污染系统环境）

设计约束：
    - 所有子进程调用带超时，防止 pip 网络卡顿拖垮实验；
    - venv 按"缺失包集合"做磁盘缓存（~/.cache/aitester/venvs/<hash>/），
      相同依赖组合的任务复用同一 venv，避免每个任务都重建（重建约 1-3s）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger(__name__)

# ─── 预编译正则：与 executor._extract_imports 同源语义 ───────────────────────
_RE_FROM_IMPORT = re.compile(r"from\s+([\w.]+)\s+import")
_RE_IMPORT = re.compile(r"^import\s+([\w.]+)", re.MULTILINE)

# ─── venv 磁盘缓存目录 ───────────────────────────────────────────────────────
_VENV_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "aitester", "venvs")

# ─── 模块名 → pip 包名映射（模块名与包名不一致的常见第三方库）──────────────
# 来源：各库官方发布的推荐 pip 名（cv2→opencv-python、PIL→Pillow 等）
_MODULE_TO_PACKAGE: dict[str, str] = {
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "lxml": "lxml",
    "pydantic": "pydantic",
    "attr": "attrs",
    "gi": "PyGObject",
    "magic": "python-magic",
    "serial": "pyserial",
    "usb": "pyusb",
    "wx": "wxPython",
}

# ─── 本机 import 可用性检查缓存（进程内，避免重复 find_spec）────────────────
# 键：顶层模块名；值：bool（可 import）。find_spec 结果在进程生命周期内稳定
# （venv 安装发生在子进程，不影响宿主进程的解释器环境）
_importable_cache: dict[str, bool] = {}


def extract_imported_modules(code: str) -> set[str]:
    """提取 Python 源码中 import 的所有顶层模块名。

    覆盖两种语句：
        import os, sys / import numpy as np  → "os" "sys" "numpy"
        from collections import OrderedDict   → "collections"

    Args:
        code: Python 源码字符串。

    Returns:
        顶层模块名集合（不含相对导入 "." 开头项）。
    """
    modules: set[str] = set()
    if not code:
        return modules
    for line in code.splitlines():
        stripped = line.strip()
        match = _RE_FROM_IMPORT.match(stripped) or _RE_IMPORT.match(stripped)
        if not match:
            continue
        module_name = match.group(1)
        # 相对导入（from . import x）以 . 开头，跳过
        if module_name.startswith("."):
            continue
        top_level = module_name.split(".")[0]
        if top_level:
            modules.add(top_level)
    return modules


def is_standard_library(module_name: str) -> bool:
    """判断模块是否属于 Python 标准库。

    优先使用 sys.stdlib_module_names（3.10+ 的权威清单），
    缺失时回退保守判断（视为非 stdlib，交给 find_spec 探测）。

    Args:
        module_name: 顶层模块名。

    Returns:
        True 表示标准库模块。
    """
    stdlib_names: set[str] | None = getattr(sys, "stdlib_module_names", None)
    if stdlib_names is not None:
        return module_name in stdlib_names
    # 回退：常见标准库白名单（保守，未命中视为第三方交由探测）
    _FALLBACK_STDLIB = {
        "os", "sys", "re", "math", "json", "datetime", "collections", "itertools",
        "functools", "pathlib", "typing", "abc", "copy", "unittest", "pytest",
        "tempfile", "subprocess", "logging", "argparse", "dataclasses", "enum",
        "io", "string", "textwrap", "struct", "codecs", "unicodedata", "difflib",
        "pprint", "numbers", "cmath", "decimal", "fractions", "random", "statistics",
        "array", "bisect", "heapq", "queue", "types", "contextlib", "operator",
        "pickle", "sqlite3", "zipfile", "gzip", "shutil", "glob", "fnmatch",
        "threading", "concurrent", "multiprocessing", "asyncio", "socket", "ssl",
        "urllib", "http", "email", "xml", "html", "base64", "hashlib", "hmac",
    }
    return module_name in _FALLBACK_STDLIB


def find_missing_modules(
    module_names: set[str],
    extra_search_files: list[str] | None = None,
) -> set[str]:
    """判断给定的顶层模块名中哪些在当前环境不可用。

    判定顺序（命中即视为"可用"，不计入缺失）：
    1. 标准库模块 → 可用（无需安装）；
    2. 本机已安装（importlib.util.find_spec 命中）→ 可用；
    3. extra_search_files 中存在同名 .py 文件 → 可用（项目自带模块）；
    4. 以上都不满足 → 缺失（需要 pip install）。

    Args:
        module_names: 待检查的顶层模块名集合。
        extra_search_files: 额外源码文件路径列表（被测模块等），
            其模块名视为本地可用。

    Returns:
        缺失的模块名集合（已排除标准库和已安装模块）。
    """
    local_module_names: set[str] = set()
    for path in extra_search_files or []:
        base = os.path.splitext(os.path.basename(path))[0]
        if base:
            local_module_names.add(base)

    missing: set[str] = set()
    for name in module_names:
        if name in local_module_names:
            continue
        if is_standard_library(name):
            continue
        if _is_importable_cached(name):
            continue
        missing.add(name)
    if missing:
        logger.info("检测到缺失的第三方模块: %s", ", ".join(sorted(missing)))
    return missing


def _is_importable_cached(module_name: str) -> bool:
    """带进程级缓存的模块可导入探测（find_spec 开销较大）。"""
    cached = _importable_cache.get(module_name)
    if cached is not None:
        return cached
    try:
        spec = importlib.util.find_spec(module_name)
        result = spec is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError) as e:
        # find_spec 对某些命名空间包会抛异常，按缺失处理
        logger.debug("find_spec(%s) 异常: %s", module_name, e)
        result = False
    _importable_cache[module_name] = result
    return result


def suggest_package_names(module_names: set[str]) -> list[str]:
    """把缺失模块名映射为 pip 可安装的包名（去重，保持确定顺序）。

    已知不一致（PIL→pillow、cv2→opencv-python-headless 等）查映射表，
    未知模块默认"模块名即包名"（多数库如此）。

    Args:
        module_names: 缺失的顶层模块名集合。

    Returns:
        pip 包名列表（排序去重）。
    """
    packages = {
        _MODULE_TO_PACKAGE.get(name, name)
        for name in module_names
        if not is_standard_library(name)
    }
    return sorted(packages)


def venv_cache_dir(required_packages: list[str]) -> str:
    """按依赖组合计算 venv 缓存目录路径（相同组合复用同一 venv）。"""
    digest = hashlib.md5("|".join(sorted(required_packages)).encode()).hexdigest()[:12]
    label = "_".join(sorted(required_packages))[:40] or "bare"
    return os.path.join(_VENV_CACHE_DIR, f"{digest}_{label}")


def create_venv(venv_dir: str, timeout: int = 120) -> str:
    """创建隔离 venv（--system-site-packages 继承系统已装库，缺失的才需 pip 安装）。

    带磁盘缓存：目标目录下已有 python 解释器时直接复用（约省 1-3s）。

    Args:
        venv_dir: venv 目录路径（绝对路径）。
        timeout: 创建子进程超时秒数。

    Returns:
        venv 内 Python 解释器路径（unix: bin/python，win: Scripts/python.exe）。

    Raises:
        RuntimeError: venv 创建失败时抛出。
    """
    candidates = [
        os.path.join(venv_dir, "bin", "python"),
        os.path.join(venv_dir, "Scripts", "python.exe"),
    ]
    for interpreter in candidates:
        if os.path.exists(interpreter):
            logger.debug("复用已有 venv: %s", venv_dir)
            return interpreter

    os.makedirs(venv_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "venv", "--system-site-packages", venv_dir]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"venv 创建超时（>{timeout}s）: {venv_dir}") from e
    if proc.returncode != 0:
        raise RuntimeError(f"venv 创建失败: {proc.stderr.strip()[:300]}")
    interpreter = candidates[0] if os.path.exists(candidates[0]) else candidates[1]
    logger.info("venv 已创建: %s", venv_dir)
    return interpreter


def install_packages(
    venv_interpreter: str,
    package_names: list[str],
    timeout: int = 120,
) -> tuple[bool, str]:
    """在指定 venv 内 pip install 包列表（仅影响该 venv，不污染系统环境）。

    Args:
        venv_interpreter: venv 的 Python 解释器路径。
        package_names: pip 包名列表。
        timeout: 安装子进程超时秒数（防止网络卡顿拖垮实验）。

    Returns:
        (是否全部安装成功, 安装过程输出摘要)。
    """
    if not package_names:
        return True, ""
    cmd = [venv_interpreter, "-m", "pip", "install", "--disable-pip-version-check", *package_names]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        detail = f"pip install 超时（>{timeout}s）: {package_names}"
        logger.error(detail)
        return False, detail
    success = proc.returncode == 0
    summary = (proc.stderr or proc.stdout or "")[-300:]
    logger.info("依赖安装%s: %s", "成功" if success else "失败", " ".join(package_names))
    return success, summary
