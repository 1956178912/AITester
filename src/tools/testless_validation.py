"""
G5 执行无关（testless）修复验证（默认关）。

背景（gap_report 2026-09-28 P2 缺口 G5）：
    企业级"无测试仓库"场景下，pytest 不可用（无测试用例可跑），
    修复是否有效无法靠"测试通过"判定。需要一个"执行无关"的
    静态验证层：AST 符号守卫 + mypy 静态检查 + 命名契约回归 +
    导入冒烟，四者独立可开关，任一失败即判"修复未通过验证"。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `TESTLESS_VALIDATION_ENABLE=false`（默认）时本模块零行为变化：
      不接入工作流主链路，纯离线验证器；
    - 四层验证（AST 符号守卫 / mypy / 命名契约 / 导入冒烟）各自独立
      可开关（环境变量），mypy 层复用 TYPE_CHECK_ENABLE 既有静态检查
      能力（缺 mypy 依赖时透明降级跳过，不阻断）；
    - 导入冒烟是"仅 import 不执行"的保守口径（subprocess 跑
      `python -c "import <module>"`，超时上限可配，不 import 后
      执行任何业务函数——避免无测试场景下误触发副作用）；
    - 验证结果是纯数据（dict），供风险分级（G2）/ 实验报告消费，
      不自动改写源文件、不阻断历史执行链路。

使用方式（离线 / CI 消费）：
    from src.tools.testless_validation import testless_validation_enabled, run_testless_validation

    if testless_validation_enabled():
        result = run_testless_validation(original_code, patched_code, target_module)
        # result["passed"] / result["layers"] = {ast_symbol_guard, mypy,
        # naming_contract, import_smoke: {"passed": bool, "detail": str}}
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def testless_validation_enabled() -> bool:
    """testless 验证总开关（TESTLESS_VALIDATION_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("TESTLESS_VALIDATION_ENABLE", "false").lower() == "true"


def _layer_enabled(layer_name: str, env_name: str, default: str = "true") -> bool:
    """单层验证开关（在总开关开启时逐层独立可关，默认开）。"""
    return os.getenv(env_name, default).lower() in ("true", "1", "on")


def _import_smoke_timeout() -> int:
    """导入冒烟的 subprocess 超时（TESTLESS_IMPORT_SMOKE_TIMEOUT，默认 10s，范围 [3, 120]）。"""
    try:
        n = int(os.getenv("TESTLESS_IMPORT_SMOKE_TIMEOUT", "10"))
    except ValueError:
        n = 10
    return max(3, min(n, 120))


def _run_ast_symbol_guard(original_code: str, patched_code: str) -> dict[str, Any]:
    """AST 符号守卫：补丁不得删除原代码的模块级函数 / 类定义（保守口径）。

    与 patch_applier 的"函数定义数量不减少"检查（multi_candidate 防御网
    检查 4）同口径，但独立成层（testless 场景下不依赖 multi_candidate
    是否启用）。

    Returns:
        {"passed": bool, "detail": str}（detail 含被删符号清单）。
    """
    import ast

    def _top_level_defs(code: str) -> set[str]:
        names: set[str] = set()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return names
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
        return names

    orig_defs = _top_level_defs(original_code)
    patched_defs = _top_level_defs(patched_code)
    removed = sorted(orig_defs - patched_defs)
    if removed:
        return {"passed": False, "detail": f"AST 符号守卫失败：补丁删除了原代码的模块级定义 {removed}"}
    added = sorted(patched_defs - orig_defs)
    detail = "AST 符号守卫通过"
    if added:
        detail += f"（新增 {len(added)} 个模块级定义，不影响守卫）"
    return {"passed": True, "detail": detail}


def _run_mypy_layer(patched_code: str, target_module: str) -> dict[str, Any]:
    """mypy 静态检查层（TYPE_CHECK_ENABLE 口径，缺 mypy 依赖时保守跳过）。"""
    import subprocess
    import tempfile

    if not _layer_enabled("mypy", "TESTLESS_MYPY_ENABLE", "true"):
        return {"passed": True, "detail": "mypy 层显式关闭（TESTLESS_MYPY_ENABLE=false），跳过"}

    try:
        import mypy.api  # noqa: F401  # 探活（缺依赖时降级跳过，不阻断）
    except ImportError:
        return {"passed": True, "detail": "mypy 未安装（ADR-0004 零默认依赖口径），保守跳过"}

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(patched_code)
        tmp_path = f.name

    try:
        import sys

        result = subprocess.run(
            [
                # O35（P2）：用当前解释器而非 PATH 上的 "python"——本模块
                # sys_executable() 已为导入冒烟层统一口径（L231），mypy 层此前
                # 硬编码 "python"：venv 场景可能解析到系统解释器（缺 mypy →
                # OSError → 静默"保守跳过"，该层实际从未生效），且跳过原因
                # 只进 detail 文本，调用方无从区分"没装 mypy"与"解释器不对"。
                sys.executable,
                "-m",
                "mypy",
                "--no-error-summary",
                "--silent-imports",
                "--ignore-missing-imports",
                "--allow-redefinition",
                "--python-version",
                f"{sys.version_info.major}.{sys.version_info.minor}",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
        )
        output = (result.stdout + result.stderr).strip()
        # mypy 返回码：0 = 无错误，1 = 有类型错误，2 = 致命错误，3 = 内部错误
        if result.returncode == 0:
            return {"passed": True, "detail": "mypy 通过（0 错误）"}
        error_lines = [ln for ln in output.splitlines() if "error:" in ln or "note:" in ln]
        detail = f"mypy 发现 {len(error_lines)} 处问题（前 5 条）：" + "；".join(error_lines[:5])
        return {"passed": len(error_lines) == 0, "detail": detail}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"passed": True, "detail": f"mypy 执行失败（保守跳过，不阻断）: {e}"}
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def _run_naming_contract_layer(original_code: str, patched_code: str) -> dict[str, Any]:
    """命名契约回归层（复用 patch_applier.check_naming_contract 的 Python AST 专属实现）。"""
    if not _layer_enabled("naming_contract", "TESTLESS_NAMING_CONTRACT_ENABLE", "true"):
        return {"passed": True, "detail": "命名契约层显式关闭（TESTLESS_NAMING_CONTRACT_ENABLE=false），跳过"}
    from src.tools.patch_applier import check_naming_contract

    ok, missing = check_naming_contract(original_code, patched_code)
    if ok:
        return {"passed": True, "detail": "命名契约回归通过（无被删模块级符号）"}
    return {"passed": False, "detail": f"命名契约回归失败：缺失符号 {sorted(missing)}"}


def _run_import_smoke_layer(
    original_code: str,
    patched_code: str,
    target_module: str,
) -> dict[str, Any]:
    """导入冒烟层：exec_module 执行 LLM 补丁代码（import 本身可能执行模块级
    代码，这是 Python 语义固有行为，冒烟口径是"import 不崩"）。

    H-1 安全修复（2026-09-29）：子进程走凭证脱敏环境 + 执行前做危险 API
    静态预检（dangerous_api_added 差集口径），命中即拒跑。
    """
    import subprocess
    import tempfile

    if not _layer_enabled("import_smoke", "TESTLESS_IMPORT_SMOKE_ENABLE", "true"):
        return {"passed": True, "detail": "导入冒烟层显式关闭（TESTLESS_IMPORT_SMOKE_ENABLE=false），跳过"}

    # H-1 安全修复（2026-09-29）②：执行前对 patched_code 做危险 API 静态
    # 预检（patch_applier.dangerous_api_added 差集口径，与原代码做差集，
    # 只拦补丁**新引入**的危险调用，避免误伤原代码既有 subprocess 依赖）——
    # 命中 os.system / subprocess / eval / 网络外连 / 凭证读取时直接拒跑
    # （fail-closed，不执行），与 safe_apply_patch 的 S2 守卫同模式。
    # dangerous_api_added 纯 AST 静态检查且内部已 try/except 兜底（解析
    # 失败返回空集，不抛异常），无需外层 try/except（2026-09-29 审查
    # R2 优化：死代码移除）。
    from src.tools.patch_applier import dangerous_api_added

    _added = dangerous_api_added(original_code, patched_code)
    if _added:
        return {
            "passed": False,
            "detail": f"导入冒烟拒跑（危险 API 预检命中，不执行）: {sorted(_added)}",
        }

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(patched_code)
        tmp_path = f.name

    module_name = target_module or "import_smoke_module"
    smoke_script = (
        f"import importlib.util, sys; spec = importlib.util.spec_from_file_location({module_name!r}, {tmp_path!r}); "
        f"mod = importlib.util.module_from_spec(spec); sys.modules[{module_name!r}] = mod; spec.loader.exec_module(mod)"
    )
    timeout = _import_smoke_timeout()
    # H-1 安全修复（2026-09-29）①：子进程凭证脱敏（credential_scrub.
    # scrub_os_environ，与 executor_runtime / runtime_probe 同口径）——
    # 历史实现未传 env，LLM 凭证随完整 os.environ 继承进执行 LLM 代码的
    # 子进程，补丁含网络外连/凭证读取时即成可外传向量。
    from src.utils.credential_scrub import scrub_os_environ

    env = scrub_os_environ()
    try:
        result = subprocess.run(
            [sys_executable(), "-c", smoke_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "detail": f"导入冒烟超时（>{timeout}s）"}
    except OSError as e:
        return {"passed": True, "detail": f"导入冒烟执行失败（保守跳过，不阻断）: {e}"}
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    if result.returncode == 0:
        return {"passed": True, "detail": f"导入冒烟通过（import {module_name} 成功）"}
    tail = (result.stderr or result.stdout or "").strip()[-400:]
    return {"passed": False, "detail": f"导入冒烟失败（import {module_name} 异常）：{tail or '（无输出）'}"}


def sys_executable() -> str:
    """当前 Python 解释器路径（供导入冒烟 subprocess 复用同一解释器）。"""
    import sys

    return sys.executable


def run_testless_validation(
    original_code: str,
    patched_code: str,
    target_module: str = "",
) -> dict[str, Any]:
    """跑 testless 修复验证（四层独立可开关，纯数据输出，不写盘、不改源）。

    设计口径（保守、零 LLM 成本）：
        - 总开关 TESTLESS_VALIDATION_ENABLE=false（默认）时调用方通常不会
          调本函数；即使调用（测试 / 离线分析），也逐层按单层开关执行，
          不影响工作流主链路；
        - 四层（ast_symbol_guard / mypy / naming_contract / import_smoke）
          全部 passed=True 时整体 passed=True，任一层失败 → 整体
          passed=False（fail-closed，与"无测试场景下保守验证"口径一致）；
        - 单层失败时把该层的 detail 写进 result["layers"][layer]，
          供 G2 风险分级把"哪一层失败"作为影响面因子放大风险分。

    Args:
        original_code: 原始（待修复前）代码。
        patched_code: 修复后的代码（补丁应用产物）。
        target_module: 被测模块名（导入冒烟层用；空时用临时文件名兜底）。

    Returns:
        验证结果 dict：{"passed": bool, "layers": {...}, "failed_layers": [name, ...]}
    """
    layers: dict[str, dict[str, Any]] = {}
    layers["ast_symbol_guard"] = _run_ast_symbol_guard(original_code, patched_code)
    layers["mypy"] = _run_mypy_layer(patched_code, target_module)
    layers["naming_contract"] = _run_naming_contract_layer(original_code, patched_code)
    layers["import_smoke"] = _run_import_smoke_layer(original_code, patched_code, target_module)

    failed = [name for name, layer in layers.items() if not layer.get("passed", True)]
    overall_passed = len(failed) == 0
    result: dict[str, Any] = {
        "passed": overall_passed,
        "layers": layers,
        "failed_layers": failed,
    }
    logger.info(
        "G5 testless 验证：%s（失败层: %s）",
        "通过" if overall_passed else "未通过",
        ", ".join(failed) if failed else "无",
    )
    return result


__all__ = [
    "run_testless_validation",
    "sys_executable",
    "testless_validation_enabled",
]
