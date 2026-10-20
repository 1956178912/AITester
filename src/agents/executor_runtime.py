"""
测试执行器基础设施：子进程运行、超时重试与临时资源清理。

拆分自 executor.py（结构优化轮次）：ExecutorAgent 的类主体保留在
executor.py，本模块承载三条执行链路共用的底层能力——
带重试的 pytest 子进程执行（_run_pytest_with_retry）与临时文件/沙箱目录清理
（_cleanup_temp_file / _cleanup_sandbox）。

2026-10-18 第三方评审 A16/A13（P1）修复：
- A16：run_pytest_with_retry 保留**每次尝试记录**（rc / timed_out / passed），
  并暴露 observed_fail_then_pass / summarize_execution_attempts 纯函数供
  executor 链路与 nodes 侧消费——首败次过（fail→pass）的证据不再被最后一次
  成功结果抹掉；返回结构仍是 (output, last_result) 二元组（历史调用方与
  mock 测试逐字兼容，attempts 以 best-effort 属性挂在 last_result 上）。
- A13：新增执行前**能力检查**（check_execution_capability）：Executor 子进程
  固定 `python -m pytest ... --cov`，干净基础 wheel（无 execution extra）下
  旧实现得到 `No module named pytest` 的 rc=1 并被误分类；现在缺模块时直接
  返回结构化的 execution_dependency_missing 诊断（含安装指引），不重试。
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Any

from src.utils.env_utils import env_int

# 2026-10-10：模块级导入（而非函数内局部导入），使测试可用
# `@patch("src.agents.executor_runtime.run_with_timeout")` 稳定替换该调用点。
from src.utils.process_utils import run_with_timeout

try:
    import resource  # POSIX only; Windows 下 import 失败 → 静默降级

    _RLIMIT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RLIMIT_AVAILABLE = False

logger = logging.getLogger(__name__)

# S5 平台兜底（2026-10-01 主批次实跑发现）：macOS（Darwin）上
# resource.setrlimit(RLIMIT_AS, ...) 在 preexec_fn 内调用会抛
# SubprocessError("Exception occurred in preexec_fn")——macOS 对 RLIMIT_AS
# 的限制行为与 Linux 不同（Python 3.14 解释器 + pytest + coverage 虚拟
# 地址空间轻松超过 512MB，且 setrlimit 本身在 fork 后 exec 前对 AS
# 的限制在 Darwin 上不稳定）。此前 S5 仅检查 RLIMIT_AVAILABLE（import
# resource 成功）与平台 ∈ {Linux, Darwin}，未考虑 macOS 上 AS 限制
# 会导致**所有**子进程 pytest 直接 SubprocessError 失败（主批次 0/5
# 全失败即此原因）。
# 兜底口径：Darwin 平台**跳过** RLIMIT_AS（保留 CPU / NPROC / FSIZE /
# NOFILE 四项有效防线），Linux 保持全五项；可经 EXECUTOR_RLIMIT_AS_MB
# 设为 0 在 Linux 上手动禁用 AS 限制。
_IS_DARWIN = platform.system() == "Darwin"

# AS 限制平台兜底（2026-10-01 主批次实跑发现）：macOS（Darwin）上
# **任何** resource.setrlimit(RLIMIT_AS, ...) 调用都会抛 SubprocessError
# （本机 Python 3.14 实测：fresh 进程 RLIMIT_AS 软/硬限均为无上限，
# setrlimit(AS, 2GB) / (AS, 128GB) / (AS, current+1) 均 SubprocessError——
# Darwin 对该 rlimit 的限制整体不支持）。若强行 setrlimit(AS) 会导致
# **所有**子进程 pytest 直接失败（主批次 0/5 全失败即此原因）。
# 兜底口径：Darwin 平台**默认跳过** RLIMIT_AS（保留 CPU / NPROC /
# FSIZE / NOFILE 四项有效防线），Linux 保持全五项；显式
# EXECUTOR_RLIMIT_AS_FORCE=1 可在 Darwin 上强制启用 AS（自担风险，
# 若平台不支持会重现场）。


def _make_resource_preexec_fn() -> Any | None:
    """返回 preexec_fn 闭包（在子进程 exec 前设 resource.setrlimit）。

    契约（F04／2026-10-19 Z 轮审查修复）：每项 ``EXECUTOR_RLIMIT_*`` 的
    取值 ``> 0`` 时设置该 rlimit；取值 ``= 0`` 表示**禁用该项**（不调用
    ``setrlimit``，而不是把额度设成 0）。历史实现无条件
    ``setrlimit(..., (0, 0))``：注释承诺"0 禁用"但实际把 AS/CPU 等额度压到
    0——Linux 上 AS=0 会让子进程 exec/内存分配直接失败，与"禁用限制"语义
    相反。坏值 / 负值仍由 ``env_int(..., lo=0)`` 回退默认值（负值不会进入
    ``> 0`` 分支）。
    """
    if not _RLIMIT_AVAILABLE or (platform.system() not in ("Linux", "Darwin")):
        return None
    # J-1d（2026-10-17）：此前为裸 int(os.getenv(...))。坏值（如 EXECUTOR_RLIMIT_CPU=30s）
    # 抛的 ValueError 会被调用点的 `except Exception` 吞成 ("UNAVAILABLE", …)——即**整批**
    # 执行判分静默归零，日志里只有一行"第 N 次执行失败"；负值则让 setrlimit 在
    # preexec_fn 内抛错、伪装成 SubprocessError。lo=0 保留"设 0 即禁用该项"的既有口径
    # （F04 起该口径在 _preexec_fn 内真正落地：0 = 跳过对应 setrlimit）。
    _cpu_limit = env_int("EXECUTOR_RLIMIT_CPU", 300, lo=0)
    _as_limit_mb = env_int("EXECUTOR_RLIMIT_AS_MB", 512, lo=0)
    _nproc_limit = env_int("EXECUTOR_RLIMIT_NPROC", 512, lo=0)
    _FSIZE_limit_mb = env_int("EXECUTOR_RLIMIT_FSIZE_MB", 100, lo=0)
    _nofile_limit = env_int("EXECUTOR_RLIMIT_NOFILE", 256, lo=0)
    # Darwin 平台兜底：默认跳过 AS（setrlimit(AS) 在 macOS 上整体不支持）；
    # 显式 EXECUTOR_RLIMIT_AS_FORCE=1 时强制启用（Linux 口径不变）。
    # J-2 定调：此开关**刻意不并入** env_flag/env_flag_opt_out——正集口径会把
    # EXECUTOR_RLIMIT_AS_FORCE=true 读成"强制启用 AS"，而 Darwin 上任何 setrlimit(AS)
    # 都会让**全部**子进程 pytest 失败（S5 实跑 0/5 即此因）。窄口径（只认 "1"）
    # 是正确的 fail-safe 方向：无法识别的值 = 不强制 = 按平台跳过 AS。
    _as_force = os.getenv("EXECUTOR_RLIMIT_AS_FORCE", "0") == "1"
    _enable_as = _as_force or not _IS_DARWIN

    def _preexec_fn() -> None:
        # F04：逐项 ``> 0`` 守卫——0 = 该项禁用（跳过 setrlimit），见函数 docstring。
        # CPU 时间（默认 300s，到时后 SIGXCPU 终止子进程）
        if _cpu_limit > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (_cpu_limit, _cpu_limit))
        # 虚拟地址空间（Linux 全量；Darwin 默认跳过——见模块顶注：
        # setrlimit(AS) 在 macOS 上整体不支持，强设会 SubprocessError）
        if _enable_as and _as_limit_mb > 0:
            _as_bytes = _as_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (_as_bytes, _as_bytes))
        # 最大子进程数（fork 炸弹防线；非 root 时硬限生效）
        if _nproc_limit > 0:
            resource.setrlimit(resource.RLIMIT_NPROC, (_nproc_limit, _nproc_limit))
        # 文件大小（防 LLM 代码写满磁盘）
        if _FSIZE_limit_mb > 0:
            _FSIZE_bytes = _FSIZE_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_bytes, _FSIZE_bytes))
        # 文件描述符上限（防无界 open）
        if _nofile_limit > 0:
            resource.setrlimit(resource.RLIMIT_NOFILE, (_nofile_limit, _nofile_limit))

    return _preexec_fn


def _to_str(value: str | bytes | None) -> str:
    """将 subprocess.TimeoutExpired 的 output/stderr 字段安全转为字符串。

    2026-09-26 优化：从 run_pytest_with_retry 内部闭包提升为模块级函数
    （此前每次 TimeoutExpired 都重新创建闭包对象，热路径上无谓分配）。
    本调用点恒传 text=True，运行期 output/stderr 为 str 或 None；mypy 按
    类型联合（str | bytes | None）报 "+" 运算，显式转 str 收窄
    （bytes 分支仅静态可达性兜底，运行期不会触发）。
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


# ─── A16（2026-10-18 第三方评审 P1）：执行尝试记录 ─────────────────────────────
# 背景：重试层对任意非零 rc 重试，旧实现只保留 last_result——"首败次过"
# （fail→pass，同一 (target_code, generated_test) 两次执行结果不一致）的证据
# 被最后一次成功结果抹掉；nodes.py 的 flaky 门只对 passed=False 生效，因此
# 假"修复正确"可直接进入终态。修复口径：每次尝试记录 returncode / timed_out /
# passed（不记录完整输出，控制内存），挂在 last_result 的 execution_attempts
# 属性上；调用方（executor.py 本地链 / executor_modes.py 沙箱链）把序列并入
# 结果 dict，nodes 侧按真实序列写 flaky 标记并保守处理 test_passed。
# 兼容性：返回结构保持 (output, last_result) 二元组；标记元组
# ("EARLY_RETURN"/"UNAVAILABLE", error_info) 与 None 语义逐字不变，attempts
# 以 best-effort 方式挂载（tuple 无法 setattr 时静默跳过，不改变返回）。
_EXECUTION_ATTEMPTS_ATTR = "execution_attempts"


def _execution_attempt_record(
    attempt: int,
    returncode: Any,
    *,
    timed_out: bool = False,
    error_type: str | None = None,
) -> dict[str, Any]:
    """构造单次执行尝试记录（纯数据，JSON 可序列化）。"""
    record: dict[str, Any] = {
        "attempt": attempt,
        "returncode": returncode,
        "timed_out": bool(timed_out),
        "passed": returncode == 0 and not timed_out,
    }
    if error_type:
        record["error_type"] = error_type
    return record


def _attach_execution_attempts(last_result: Any, attempts: list[dict[str, Any]]) -> Any:
    """把尝试记录 best-effort 挂到 last_result（tuple / 不可写对象静默跳过）。"""
    try:
        setattr(last_result, _EXECUTION_ATTEMPTS_ATTR, [dict(a) for a in attempts])
    except Exception:  # 观测层 best-effort，绝不影响执行返回
        logger.debug("执行尝试记录挂载失败（非关键观测层，跳过）: %r", last_result)
    return last_result


def extract_execution_attempts(last_result: Any) -> list[dict[str, Any]]:
    """从 run_pytest_with_retry 的返回项恢复每次尝试记录（缺失时返回空列表）。"""
    raw = getattr(last_result, _EXECUTION_ATTEMPTS_ATTR, None)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def observed_fail_then_pass(attempts: list[dict[str, Any]] | None) -> bool:
    """是否观察到"先失败、后通过"的尝试序列（同一测试同代码重试）。

    判定口径：按执行顺序扫描，任一**之前出现过失败**的尝试 passed=True
    即为 fail→pass（与重试层"仅非零 rc 才继续"的控制流一致；记录缺失 /
    顺序不可用时保守返回 False，不臆测）。
    """
    saw_failure = False
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        if attempt.get("passed"):
            if saw_failure:
                return True
        else:
            saw_failure = True
    return False


def summarize_execution_attempts(attempts: list[dict[str, Any]] | None) -> dict[str, Any]:
    """汇总尝试序列（供 nodes 侧 flaky 字段与统计消费）。"""
    records = [a for a in (attempts or []) if isinstance(a, dict)]
    pass_count = sum(1 for a in records if a.get("passed"))
    timed_out_count = sum(1 for a in records if a.get("timed_out"))
    return {
        "attempts": len(records),
        "pass_count": pass_count,
        "fail_count": len(records) - pass_count,
        "timed_out_count": timed_out_count,
        "fail_then_pass": observed_fail_then_pass(records),
    }


# ─── A13（2026-10-18 第三方评审 P1）：执行运行依赖能力检查 ────────────────────
# 背景：Executor 子进程固定 `python -m pytest ... --cov`（executor.py 本地链 /
# executor_modes.py venv 沙箱链），但 pytest / pytest-cov 此前只在 dev extra；
# 干净基础 wheel 安装后执行路径得到 `No module named pytest` 的 rc=1，被错误
# 分类器归为 test_failure（晦涩失败 + 测量污染）。修复：发行面新增 execution
# extra（pyproject.toml / setup.py），并在子进程执行**前**对实际解释器做能力
# 探测——缺模块时直接早退为 execution_dependency_missing（清晰错误 + 安装
# 指引），不重试、不误分类。探测只做"模块是否可导入"，不改变 passed 语义。
_EXECUTION_MODULE_PACKAGES: dict[str, str] = {
    "pytest": "pytest",
    "pytest_cov": "pytest-cov",
    "pytest_timeout": "pytest-timeout",
}
_EXECUTION_INSTALL_HINT = 'pip install "aitester[execution]"'
# 探测结果缓存：key = (规范化解释器路径, 必需模块元组)。进程内解释器/依赖
# 组合不会在执行批次中途变化，缓存避免 venv 链路每次执行都起探测子进程。
_EXECUTION_CAPABILITY_CACHE: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
# 解释器 basename 白名单：python / python3 / python3.14 / python.exe ……
# 用于从（可能被内核沙箱包装的）argv 中定位真正执行 pytest 的解释器。
_PYTHON_EXE_RE = re.compile(r"^python(?:\d+(?:\.\d+)*)?(?:\.exe)?$", re.IGNORECASE)
_PROBE_MODULES_SCRIPT = (
    "import importlib.util, json, sys\n"
    "result = {}\n"
    "for name in sys.argv[1:]:\n"
    "    try:\n"
    "        result[name] = importlib.util.find_spec(name) is not None\n"
    "    except Exception:\n"
    "        result[name] = False\n"
    "print(json.dumps(result))\n"
)


def clear_execution_capability_cache() -> None:
    """清空能力探测缓存（测试隔离 / 运行期显式重探测用）。"""
    _EXECUTION_CAPABILITY_CACHE.clear()


def _is_current_interpreter(interpreter: str) -> bool:
    """解释器是否就是当前进程解释器（可零开销在进程内探测）。"""
    try:
        return os.path.normcase(os.path.realpath(interpreter)) == os.path.normcase(os.path.realpath(sys.executable))
    except OSError:  # pragma: no cover - 路径解析失败时保守走子进程探测
        return False


def _probe_modules_in_process(modules: tuple[str, ...]) -> dict[str, bool]:
    """在当前进程内探测模块可导入性（sys.executable 路径零子进程开销）。"""
    import importlib.util

    found: dict[str, bool] = {}
    for module in modules:
        try:
            found[module] = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found[module] = False
    return found


def _probe_modules_subprocess(
    interpreter: str,
    modules: tuple[str, ...],
    env: dict[str, str] | None = None,
) -> tuple[dict[str, bool] | None, str | None]:
    """用目标解释器探测模块可导入性；探测基础设施失败返回 (None, error)。"""
    try:
        proc = subprocess.run(
            [interpreter, "-c", _PROBE_MODULES_SCRIPT, *modules],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:300]
        return None, f"exit {proc.returncode}: {stderr}"
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        return None, "probe 无输出"
    try:
        parsed = json.loads(lines[-1])
    except ValueError as exc:
        return None, f"probe 输出不可解析: {exc}"
    if not isinstance(parsed, dict):
        return None, "probe 输出结构非法"
    return {str(k): bool(v) for k, v in parsed.items()}, None


def _probe_interpreter_modules(
    interpreter: str,
    modules: tuple[str, ...],
    env: dict[str, str] | None = None,
) -> tuple[dict[str, bool] | None, str | None]:
    """按解释器是否当前进程选择进程内 / 子进程探测。"""
    if _is_current_interpreter(interpreter):
        return _probe_modules_in_process(modules), None
    return _probe_modules_subprocess(interpreter, modules, env=env)


def check_execution_capability(
    interpreter: str | None = None,
    *,
    require_coverage: bool = True,
    require_timeout_plugin: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """执行前能力检查：目标解释器是否具备 pytest 执行所需模块。

    Args:
        interpreter: 将执行 pytest 的 Python 解释器（默认当前进程解释器）。
        require_coverage: 命令带 `--cov` 时需要 pytest-cov。
        require_timeout_plugin: 命令带 `--timeout` 时需要 pytest-timeout。
        env: 子进程探测环境（与执行环境同口径；None = 继承当前环境）。

    Returns:
        {"available": bool, "interpreter": str, "required_modules": [...],
         "missing_modules": [...], "missing_packages": [...],
         "install_hint": str, "probe": "in_process"|"subprocess"|"failed",
         "probe_error": str | None}

    探测基础设施自身失败（解释器无法启动等）时保守返回 available=True 且
    probe="failed"——不因探测失败而阻断执行（交回执行层给出真实错误）；
    缺模块仅在探测**成功**时报告。
    """
    target = interpreter or sys.executable
    required: list[str] = ["pytest"]
    if require_coverage:
        required.append("pytest_cov")
    if require_timeout_plugin:
        required.append("pytest_timeout")
    required_tuple = tuple(required)
    cache_key = (os.path.normcase(os.path.realpath(target)), required_tuple)
    cached = _EXECUTION_CAPABILITY_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    modules, probe_error = _probe_interpreter_modules(target, required_tuple, env=env)
    if modules is None:
        return {
            "available": True,
            "interpreter": target,
            "required_modules": required,
            "missing_modules": [],
            "missing_packages": [],
            "install_hint": _EXECUTION_INSTALL_HINT,
            "probe": "failed",
            "probe_error": probe_error,
        }
    missing_modules = [module for module in required if not modules.get(module)]
    result: dict[str, Any] = {
        "available": not missing_modules,
        "interpreter": target,
        "required_modules": required,
        "missing_modules": missing_modules,
        "missing_packages": [_EXECUTION_MODULE_PACKAGES[m] for m in missing_modules],
        "install_hint": _EXECUTION_INSTALL_HINT,
        "probe": "in_process" if _is_current_interpreter(target) else "subprocess",
        "probe_error": None,
    }
    _EXECUTION_CAPABILITY_CACHE[cache_key] = dict(result)
    return result


def build_execution_dependency_error(capability: dict[str, Any]) -> dict[str, Any]:
    """把能力检查结果转为 Executor 结果 dict 的 error_info（清晰、可操作）。"""
    missing_modules = list(capability.get("missing_modules") or [])
    missing_packages = list(capability.get("missing_packages") or [])
    interpreter = str(capability.get("interpreter") or "")
    module_text = ", ".join(missing_modules)
    return {
        "type": "execution_dependency_missing",
        "message": (
            f"执行环境缺少 pytest 执行依赖（{module_text}），无法运行测试；"
            f"请安装 execution extra：{_EXECUTION_INSTALL_HINT}"
        ),
        "detail": (
            f"解释器 {interpreter} 缺少模块 [{module_text}]；等价安装：pip install {' '.join(missing_packages)}"
        ),
        "missing_modules": missing_modules,
        "missing_packages": missing_packages,
        "interpreter": interpreter,
        "install_hint": _EXECUTION_INSTALL_HINT,
    }


def _command_python_interpreter(cmd: list[str]) -> str | None:
    """从执行命令中定位 Python 解释器（兼容内核沙箱包装后的 argv）。

    只认 basename 形如 python / python3 / python3.14 / python.exe 的参数，
    且要求路径存在或可经 PATH 解析（否则视为不可探测，交回执行层处理
    FileNotFoundError 等真实错误，避免把"解释器不存在"误报成"缺模块"）。
    """
    for token in cmd:
        if not isinstance(token, str):
            continue
        if not _PYTHON_EXE_RE.match(os.path.basename(token)):
            continue
        if os.path.isabs(token):
            if os.path.exists(token):
                return token
            continue
        resolved = shutil.which(token)
        if resolved:
            return resolved
    return None


def run_pytest_with_retry(self, cmd: list[str], env: dict[str, str], project_root: str) -> tuple[str, Any]:
    """
    带重试的 pytest 执行逻辑，最多尝试 2 次。
    超时/环境问题直接返回 EARLY_RETURN 标记，其他异常仅记录日志并保留最近一次有效结果。

    由 ExecutorAgent 实例调用（self.timeout 为单次超时秒数）。

    Returns:
        (output, last_result) 元组：last_result 为 subprocess.CompletedProcess、
        ("EARLY_RETURN", error_info) / ("UNAVAILABLE", error_info) 标记元组或 None。
        2026-09-26 round9 P2：通用异常不再把 last_result 置 None（保留最近一次
        有效结果，仅追加异常现场文本）；无任何有效结果时返回 ("UNAVAILABLE", …)
        标记，下游按 EARLY_RETURN 分支处理（isinstance(last_result, tuple) 统一）。

        2026-10-18 A16（P1）：正常返回路径的 CompletedProcess 类 last_result 上
        以 best-effort 方式挂载 execution_attempts（每次尝试的
        returncode / timed_out / passed 记录）；早退 error_info 内嵌 attempts。
        返回二元组结构不变（历史调用方 / 12 个 mock 测试逐字兼容）。
        2026-10-18 A13（P1）：执行前对命令中的 Python 解释器做 pytest 能力检查，
        缺 pytest / pytest-cov 时返回 EARLY_RETURN + execution_dependency_missing
        诊断（含安装指引），不再以晦涩的 rc=1 被误分类。
    """
    # A13（P1）：执行前能力检查——缺 pytest / pytest-cov 时给清晰诊断。
    interpreter = _command_python_interpreter(cmd)
    if interpreter is not None:
        capability = check_execution_capability(
            interpreter,
            require_coverage=any(isinstance(arg, str) and arg.startswith("--cov") for arg in cmd),
            require_timeout_plugin=any(isinstance(arg, str) and arg.startswith("--timeout") for arg in cmd),
            env=env,
        )
        if not capability.get("available"):
            dependency_error = build_execution_dependency_error(capability)
            logger.error("A13 执行依赖能力检查未通过：%s", dependency_error["message"])
            # output 同步返回可读消息（调用方 early-return 分支把 output 原样
            # 写进结果 dict，便于工件/调试直接看到安装指引）。
            return dependency_error["message"], ("EARLY_RETURN", dependency_error)

    max_attempts = 2
    last_output = ""
    # 2026-09-26 round9 P2：last_result 类型为 CompletedProcess | tuple | None——
    # ("EARLY_RETURN"/"UNAVAILABLE", error_info) 标记元组与 None（未运行）
    # 三种形态之一；mypy 需显式 Any 联合（历史调用方按 .returncode 属性访问
    # CompletedProcess，标记元组由 isinstance(last_result, tuple) 守卫分流）。
    last_result: Any = None
    # 2026-10-18 A16（P1）：每次尝试记录（rc / timed_out / passed）。旧实现只
    # 保留 last_result——首败次过（fail→pass）证据被最后一次成功抹掉，flaky
    # 门（仅对 passed=False 生效）永远看不到。记录不落完整输出（控内存）。
    attempts: list[dict[str, Any]] = []

    for attempt in range(max_attempts):
        try:
            # S5（2026-09-29 审查 P0）：子进程资源限制（preexec_fn + rlimit）
            # —— 此前仅约束墙钟（timeout=self.timeout），无 rlimit：
            # LLM 生成代码内 fork 炸弹 / 大内存 / 无界 print 可打满宿主
            # RSS / fd / 进程表。现通过 preexec_fn 在子进程 exec 前
            # 设 resource.setrlimit（POSIX；Windows 静默跳过，历史不变）。
            _preexec = _make_resource_preexec_fn()
            _preexec_fn_arg = {"preexec_fn": _preexec} if _preexec is not None else {}
            # 2026-10-10 独立审查修复（P0，实跑两次复现 + 敌意场景对照实证）：
            # 改建在 `src.utils.process_utils.run_with_timeout` 之上。
            #
            # 根因：`subprocess.run(timeout=)` 用 **PIPE + communicate()**，超时只
            # `kill()` 直接子进程；被测缺陷若死循环（本批实测 `to_base`、`bitcount`），
            # pytest 的孙进程继续持有管道写端 → `communicate()` 等 EOF **永久阻塞**
            # → 整臂挂死、批次 JSON 从不写出。
            # 实证（同一敌意场景：孙进程 start_new_session 脱离进程组后持续写 stdout）：
            #   旧实现：killpg 后 15s 宽限内仍收不回（复现挂死）
            #   新实现：4.0s 返回（timed_out=True，仍捕获到 120 字符部分输出）
            # 根因级修法是 run_with_timeout 改用**临时文件**承接 stdout/stderr：
            # 父进程读取不依赖 EOF，"孙进程持写端"在结构上不再造成阻塞。
            #
            # 返回契约保持不变：`raise_on_timeout=True` 使超时仍抛
            # `subprocess.TimeoutExpired`（携带 .stdout/.stderr 部分输出），
            # 故下方 except 分支与既有 12 个 mock 测试的假设逐字不变；
            # `check=False` 保持"按 returncode 判定"的本仓统一口径（PLW1510）。
            result = run_with_timeout(
                cmd,
                timeout=self.timeout,
                cwd=project_root,
                env=env,
                logger_name="executor_runtime",
                raise_on_timeout=True,
                check=False,
                **_preexec_fn_arg,
            )
            last_result = result
            last_output = result.stdout + result.stderr
            # A16：记录本次尝试（rc / timed_out / passed）。run_with_timeout 在
            # raise_on_timeout=True 下超时走 TimeoutExpired，故此处 timed_out
            # 恒 False（保留 getattr 以兼容未来返回契约变化）。
            attempts.append(
                _execution_attempt_record(
                    attempt + 1,
                    result.returncode,
                    timed_out=bool(getattr(result, "timed_out", False)),
                )
            )
            if result.returncode == 0:
                break
            logger.warning("第 %d 次执行失败，尝试重试...", attempt + 1)
        except subprocess.TimeoutExpired as e:
            attempts.append(_execution_attempt_record(attempt + 1, None, timed_out=True, error_type="timeout"))
            # 本调用点恒传 text=True，运行期 output/stderr 为 str 或 None；
            # _to_str 收窄类型联合（bytes 分支仅静态可达性兜底）。
            # 追加进 last_output（而非覆盖），让下游 Debugger 能拿到前次有效
            # 输出 + 本次超时快照，而非仅超时的部分文本。
            # 2026-09-26 round10 P2：旧实现 last_output = partial_output 直接
            # 覆盖，第 1 次执行失败（rc≠0）后第 2 次超时且部分输出为空时，
            # 下游丢失第 1 次的真实 pytest 输出（修复线索）——对齐 round9 通用
            # 异常分支的追加口径。单次超时场景 last_output 原为空串，结果不变。
            partial_output = _to_str(e.output) + _to_str(e.stderr)
            last_output = (
                f"{last_output or ''}\n[timeout attempt {attempt + 1}] {partial_output}"
                if last_output
                else partial_output
            )
            error_msg = f"测试执行超时（>{self.timeout}s）"
            logger.error("测试执行超时（>%ds）: %s", self.timeout, e)
            error_info = {
                "type": "timeout",
                "message": error_msg,
                "timeout_seconds": self.timeout,
                "command": " ".join(cmd[:5]) if len(cmd) > 5 else " ".join(cmd),
                # A16：早退路径（无正常返回对象可挂属性）把尝试记录内嵌进
                # error_info，供调用方/工件保留真实序列。
                "attempts": [dict(a) for a in attempts],
            }
            # 超时/环境错误需由调用方直接 return，这里用特殊标记
            return last_output, ("EARLY_RETURN", error_info)
        except FileNotFoundError as e:
            attempts.append(_execution_attempt_record(attempt + 1, None, error_type="file_not_found"))
            error_msg = "执行环境错误（找不到 pytest 或 Python 解释器）"
            logger.error("执行环境错误（找不到 pytest）: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "file_not_found",
                    "message": error_msg,
                    "detail": str(e),
                    "attempts": [dict(a) for a in attempts],
                },
            )
        except PermissionError as e:
            attempts.append(_execution_attempt_record(attempt + 1, None, error_type="permission_error"))
            error_msg = "权限不足，无法执行测试文件"
            logger.error("权限错误: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "permission_error",
                    "message": error_msg,
                    "file_path": str(e.filename) if hasattr(e, "filename") else "",
                    "attempts": [dict(a) for a in attempts],
                },
            )
        except Exception as e:
            error_msg = f"测试执行异常: {type(e).__name__}: {e}"
            logger.error("测试执行异常: %s", e)
            attempts.append(_execution_attempt_record(attempt + 1, None, error_type="execution_exception"))
            # 2026-09-26 round9 P2：通用异常不销毁 last_result（保留最近一次
            # 有效结果），仅追加异常现场文本。旧实现在第 2 次重试抛通用异常
            # 时把第 1 次失败的 last_result 置 None → 下游判"未运行"，丢失
            # 第 1 次的真实测试输出（passed/failed_cases 全空）。保守修复：
            # 有 last_result 时仅追加文本，无时标记 "UNAVAILABLE"（与 EARLY_RETURN
            # 同走 EARLY_RETURN 分支下游不会误读 .returncode）。
            if last_result is None:
                last_result = (
                    "UNAVAILABLE",
                    {
                        "type": "execution_exception",
                        "message": error_msg,
                        "attempts": [dict(a) for a in attempts],
                    },
                )
                last_output = error_msg
            else:
                last_output = f"{last_output or ''}\n[retry {attempt + 1} exception] {error_msg}"
            break

    # A16：把尝试记录挂到正常返回对象上（tuple 标记不可 setattr，其 error_info
    # 已内嵌 attempts；best-effort 失败不影响历史返回契约）。
    last_result = _attach_execution_attempts(last_result, attempts)
    return last_output, last_result


def cleanup_temp_file(test_file: str) -> None:
    """清理临时测试文件，失败时仅记录警告。"""
    try:
        if os.path.exists(test_file):
            os.unlink(test_file)
            logger.debug("已清理临时测试文件: %s", test_file)
    except OSError as e:
        logger.warning("清理临时文件失败: %s", e)


def cleanup_sandbox(sandbox_dir: str) -> None:
    """清理沙箱临时目录，失败仅记录警告（venv 缓存目录不受影响）。"""
    try:
        if os.path.isdir(sandbox_dir):
            import shutil

            shutil.rmtree(sandbox_dir, ignore_errors=True)
            logger.debug("已清理沙箱目录: %s", sandbox_dir)
    except OSError as e:
        logger.warning("清理沙箱目录失败: %s", e)
