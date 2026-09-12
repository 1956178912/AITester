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
import json
import logging
import os
import re
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

# ─── 预编译正则：import 语句提取的单一来源（executor._extract_imports 复用）──
# from 形式：捕获模块路径（可含点，相对导入以 . 开头）
_RE_FROM_IMPORT = re.compile(r"from\s+([\w.]+)\s+import")
# import 形式：捕获整行模块子句（逗号分隔多模块 + as 别名），
# 旧的 ^import\s+([\w.]+) 只能捕获首个模块，import numpy, scipy 会漏掉 scipy
_RE_IMPORT_CLAUSE = re.compile(r"^import\s+(.+)$")


def extract_import_module_names(code: str) -> list[str]:
    """逐行提取 import 语句导入的模块名（保留点号，按出现顺序）。

    覆盖三种形式：
        import os, sys                → "os", "sys"（逗号分隔多模块）
        import numpy.random as nr     → "numpy.random"（as 别名 + 点号）
        from collections import X     → "collections"
    相对导入（from . import x / from .foo import y）跳过。

    本函数是 import 提取的单一实现（DRY）：executor._extract_imports 直接复用，
    避免跨模块复制同一份正则导致缺陷同步扩散（此前逗号 import 漏检就因复制
    了两份实现而双重存在）。

    Args:
        code: Python 源码字符串。

    Returns:
        模块名列表（可含重复，保持原顺序，调用方按需去重/取顶层）。
    """
    names: list[str] = []
    if not code:
        return names
    for line in code.splitlines():
        stripped = line.strip()
        from_match = _RE_FROM_IMPORT.match(stripped)
        if from_match:
            module_name = from_match.group(1)
            if not module_name.startswith("."):
                names.append(module_name)
            continue
        import_match = _RE_IMPORT_CLAUSE.match(stripped)
        if import_match:
            # 逗号分隔多项，逐项去掉 "as 别名" 与首尾空白（尾随注释按 # 截断）
            clause = import_match.group(1).split("#", 1)[0]
            for part in clause.split(","):
                module_name = part.strip().split(" as ")[0].strip()
                if module_name:
                    names.append(module_name)
    return names


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

    覆盖：
        import os, sys / import numpy as np  → "os" "sys" "numpy"
        from collections import OrderedDict   → "collections"

    底层复用 extract_import_module_names（逗号分隔多模块完整捕获）。

    Args:
        code: Python 源码字符串。

    Returns:
        顶层模块名集合（不含相对导入 "." 开头项）。
    """
    return {name.split(".")[0] for name in extract_import_module_names(code) if name}


def is_standard_library(module_name: str) -> bool:
    """判断模块是否属于 Python 标准库。

    使用 sys.stdlib_module_names（3.10+ 的权威清单，项目 python_requires>=3.12
    保证恒存在）。此前另维护一份回退白名单（Python 3.12 下为死代码），且其中
    误将第三方 pytest 列入标准库——一旦回退生效会把 pytest 当 stdlib 跳过安装；
    白名单已删除，极端缺失场景返回 False 交由 find_spec 探测实际可用性。

    Args:
        module_name: 顶层模块名。

    Returns:
        True 表示标准库模块。
    """
    stdlib_names: set[str] | None = getattr(sys, "stdlib_module_names", None)
    if stdlib_names is None:
        # 非标准解释器（缺失权威清单）：视为非 stdlib，交给 find_spec 探测
        return False
    return module_name in stdlib_names


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
    packages = {_MODULE_TO_PACKAGE.get(name, name) for name in module_names if not is_standard_library(name)}
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
            # 4.4 缓存命中统计：记录复用事件
            _record_venv_cache_event("hit")
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
    # 4.4 缓存命中统计：记录新建事件
    _record_venv_cache_event("create")
    logger.info("venv 已创建: %s", venv_dir)
    return interpreter


# ─── 4.4 venv 缓存监控与清理 ────────────────────────────────────────────────────
# 命中率统计：进程内累计 hit/create 事件；落盘 JSON 供跨进程聚合
# （~/.cache/aitester/venvs/cache_stats.json）
_VENV_CACHE_STATS_FILE = os.path.join(_VENV_CACHE_DIR, "cache_stats.json")
_venv_cache_stats_lock = __import__("threading").Lock()
_venv_cache_stats: dict[str, Any] = {"hits": 0, "creates": 0, "last_event_at": None}


def _load_cache_stats() -> dict[str, Any]:
    """读取落盘的缓存统计（不存在或损坏时返回零值）。"""
    try:
        with open(_VENV_CACHE_STATS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {"hits": int(data.get("hits", 0)), "creates": int(data.get("creates", 0)), "last_event_at": data.get("last_event_at")}
    except (OSError, ValueError, TypeError):
        pass
    return {"hits": 0, "creates": 0, "last_event_at": None}


def _persist_cache_stats() -> None:
    """把进程内统计合并写回落盘 JSON。

    注意：本函数假设调用方已持有 _venv_cache_stats_lock（_record_venv_cache_event
    与 get_venv_cache_stats 均在锁内调用），因此不再二次加锁——threading.Lock
    不可重入，自嵌套会死锁挂起进程（09-14 4.4 批次踩坑）。
    """
    disk = _load_cache_stats()
    merged = {
        "hits": disk.get("hits", 0) + _venv_cache_stats["hits"],
        "creates": disk.get("creates", 0) + _venv_cache_stats["creates"],
        "last_event_at": _venv_cache_stats["last_event_at"],
    }
    _venv_cache_stats["hits"] = 0
    _venv_cache_stats["creates"] = 0
    try:
        os.makedirs(os.path.dirname(_VENV_CACHE_STATS_FILE), exist_ok=True)
        with open(_VENV_CACHE_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f)
    except OSError as e:
        logger.debug("venv 缓存统计落盘失败（不影响主流程）: %s", e)


def _record_venv_cache_event(kind: str) -> None:
    """记录一次缓存事件（hit/create）到进程内统计并落盘。"""
    with _venv_cache_stats_lock:
        if kind == "hit":
            _venv_cache_stats["hits"] += 1
        elif kind == "create":
            _venv_cache_stats["creates"] += 1
        _venv_cache_stats["last_event_at"] = time.time()
        _persist_cache_stats()


def get_venv_cache_stats() -> dict[str, Any]:
    """返回 venv 缓存命中率统计（4.4）。

    Returns:
        {"hits": int, "creates": int, "total": int,
         "hit_rate": float（hits/(hits+creates)，0.0 当 total=0）,
         "last_event_at": float | None}
    """
    with _venv_cache_stats_lock:
        disk = _load_cache_stats()
        hits = disk.get("hits", 0) + _venv_cache_stats["hits"]
        creates = disk.get("creates", 0) + _venv_cache_stats["creates"]
    total = hits + creates
    return {
        "hits": hits,
        "creates": creates,
        "total": total,
        "hit_rate": round(hits / total, 4) if total else 0.0,
        "last_event_at": disk.get("last_event_at"),
    }


def list_venv_cache() -> list[dict[str, Any]]:
    """列出 venv 缓存目录下所有已创建的 venv（4.4 监控）。

    Returns:
        每项 {"name": 目录名, "path": 绝对路径, "size_mb": float, "created_at": str}；
        目录不存在时返回空列表。
    """
    if not os.path.isdir(_VENV_CACHE_DIR):
        return []
    result: list[dict[str, Any]] = []
    for entry in sorted(os.listdir(_VENV_CACHE_DIR)):
        full = os.path.join(_VENV_CACHE_DIR, entry)
        if not os.path.isdir(full):
            continue
        # 统计目录大小（MB，忽略读取失败）
        size_mb = 0.0
        for root, _dirs, files in os.walk(full):
            for fname in files:
                try:
                    size_mb += os.path.getsize(os.path.join(root, fname)) / (1024 * 1024)
                except OSError:
                    continue
        try:
            created_at = str(int(os.path.getctime(full)))
        except OSError:
            created_at = "unknown"
        result.append({"name": entry, "path": full, "size_mb": round(size_mb, 2), "created_at": created_at})
    return result


def clear_venv_cache(max_age_days: int | None = None, max_size_mb: int | None = None) -> dict[str, Any]:
    """清理 venv 缓存目录（4.4）。

    按 max_age_days（按目录 mtime 判老）与 max_size_mb（按目录大小判超）过滤，
    任一条件命中即删除；两者均 None 时清空整个缓存目录。

    Args:
        max_age_days: 超过该天数的 venv 删除（None 表示不按年龄过滤）。
        max_size_mb: 超过该大小的 venv 删除（None 表示不按大小过滤）。

    Returns:
        {"removed": [name...], "kept": [name...], "freed_mb": float}
    """
    if not os.path.isdir(_VENV_CACHE_DIR):
        return {"removed": [], "kept": [], "freed_mb": 0.0}
    now = time.time()
    removed: list[str] = []
    kept: list[str] = []
    freed_mb = 0.0
    for entry in sorted(os.listdir(_VENV_CACHE_DIR)):
        full = os.path.join(_VENV_CACHE_DIR, entry)
        if not os.path.isdir(full):
            continue
        # 统计目录大小
        size_mb = 0.0
        for root, _dirs, files in os.walk(full):
            for fname in files:
                try:
                    size_mb += os.path.getsize(os.path.join(root, fname)) / (1024 * 1024)
                except OSError:
                    continue
        age_days = (now - os.path.getmtime(full)) / 86400.0
        should_remove = False
        if max_age_days is not None and age_days > max_age_days:
            should_remove = True
        if max_size_mb is not None and size_mb > max_size_mb:
            should_remove = True
        if max_age_days is None and max_size_mb is None:
            should_remove = True
        if should_remove:
            import shutil

            try:
                shutil.rmtree(full, ignore_errors=True)
                removed.append(entry)
                freed_mb += size_mb
            except OSError:
                kept.append(entry)
        else:
            kept.append(entry)
    return {"removed": removed, "kept": kept, "freed_mb": round(freed_mb, 2)}


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
