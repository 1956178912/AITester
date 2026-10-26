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
        # naming_contract, import_smoke: {"passed": bool, "detail": str,
        # "status": "ok|disabled|unavailable|error"[, "reason": str]}}
        # result["validation_status"] / result["degraded_layers"]：整体可测量性
        # —— passed=True 且 validation_status != "ok" 时不构成"验证通过"的证据。
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from src.utils.env_utils import env_flag

logger = logging.getLogger(__name__)

# BH 轮（2026-10-21）：四层验证的状态词汇与 BG 轮 type_repair 的静态检查
# 状态取值逐字一致（ok / disabled / unavailable / error），但**聚合方向相反**：
# type_repair 的两个后端是同一检查的可替代实现（任一 ok ⇒ 整体可测量），
# 本模块四层是相互独立的检查（任一层不可测量 ⇒ 整体验证不完整），故取
# 最差者。语义：
#   ok          本层确实执行完成且报告可信 ⇒ passed 可作证据
#   disabled    按设计未检查（开关关 / 拒跑）⇒ passed=True 不是"干净"的证据
#   unavailable 依赖或解释器缺席，预期降级 ⇒ 同上
#   error       本层跑了但没产出可信报告（超时 / 崩溃 / rc 异常 / 输入不可解析）
#               ⇒ **不可测量**，passed 不得当作"验证通过"
VALIDATION_OK = "ok"
VALIDATION_DISABLED = "disabled"
VALIDATION_UNAVAILABLE = "unavailable"
VALIDATION_ERROR = "error"

# 最差者优先（error > unavailable > disabled > ok）。
_STATUS_PRECEDENCE = (VALIDATION_ERROR, VALIDATION_UNAVAILABLE, VALIDATION_DISABLED, VALIDATION_OK)


def _worst_layer_status(layers: dict[str, dict[str, Any]]) -> str:
    """把逐层 status 聚合为整体验证状态（最差者优先）。

    Args:
        layers: ``run_testless_validation`` 收集的四层结果。

    Returns:
        聚合状态；未知/缺失 status 按 ``error`` 保守处理（fail-closed）。
    """
    statuses = [layer.get("status") for layer in layers.values()]
    for candidate in _STATUS_PRECEDENCE:
        if any(status == candidate for status in statuses):
            return candidate
    return VALIDATION_ERROR


def _unparseable_side(original_code: str, patched_code: str) -> str | None:
    """判定 AST 层的输入是否可解析（不可解析 ⇒ 该层根本没做比较）。

    Returns:
        ``"unparseable_original"`` / ``"unparseable_patched"`` / ``None``（两侧均可解析）。
    """
    import ast

    for side, code in (("unparseable_original", original_code), ("unparseable_patched", patched_code)):
        try:
            ast.parse(code)
        except (SyntaxError, ValueError):
            return side
    return None


def testless_validation_enabled() -> bool:
    """testless 验证总开关（TESTLESS_VALIDATION_ENABLE=true 时启用，默认 false）。"""
    return env_flag("TESTLESS_VALIDATION_ENABLE")


def _layer_enabled(layer_name: str, env_name: str, default: str = "true") -> bool:
    """单层验证开关（在总开关开启时逐层独立可关，默认开）。

    2026-10-16 C 轮收敛至 env_flag；default 为字符串字面量口径
    （"true"/"false"），转换为布尔默认值。
    """
    return env_flag(env_name, default.strip().lower() in ("true", "1", "on"))


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

    BH 轮（2026-10-21）：不可解析输入此前被折成"守卫通过"——``_top_level_defs``
    遇 SyntaxError 返回空集，于是原文不可解析 ⇒ 原符号集为空 ⇒ 差集恒空 ⇒
    ``passed=True``，与"比较过且没删符号"逐字同形（实测：原文 ``def f(:`` +
    正常补丁 → "AST 符号守卫通过（新增 1 个模块级定义，不影响守卫）"）。补丁
    不可解析时更糟：报"补丁删除了原代码的模块级定义 ['f']"，把**解析失败**
    归因成**删符号**。现两侧先判可解析性，任一侧不可解析即 status=error +
    fail-closed（passed=False），不再冒充比较结论。

    Returns:
        ``{"passed": bool, "detail": str, "status": str[, "reason": str]}``。
    """
    import ast

    unparseable = _unparseable_side(original_code, patched_code)
    if unparseable is not None:
        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"
        return {
            "passed": False,
            "status": VALIDATION_ERROR,
            "reason": unparseable,
            "detail": f"AST 符号守卫不可测量（{side}无法解析，未做任何符号比较）",
        }

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
        return {
            "passed": False,
            "status": VALIDATION_OK,
            "detail": f"AST 符号守卫失败：补丁删除了原代码的模块级定义 {removed}",
        }
    added = sorted(patched_defs - orig_defs)
    detail = "AST 符号守卫通过"
    if added:
        detail += f"（新增 {len(added)} 个模块级定义，不影响守卫）"
    return {"passed": True, "status": VALIDATION_OK, "detail": detail}


def _run_mypy_layer(patched_code: str, target_module: str) -> dict[str, Any]:
    """mypy 静态检查层（TYPE_CHECK_ENABLE 口径，缺 mypy 依赖时保守跳过）。

    BH 轮（2026-10-21）收口两类"不可测量 → 假读数"（实测于 mypy 1.15.0 /
    Python 3.14.6）：

    1. **恒不可测量（根因）**：命令行传 ``--silent-imports``，该拼写在现代
       mypy 中已不存在（正确写法 ``--follow-imports=silent``）⇒ 每次调用都
       rc=2 用法错误。旧代码把 ``mypy: error: unrecognized arguments`` 这一行
       当作**被测代码的疑点**，于是干净代码 / 类型错误代码 / 语法错误代码
       三者返回逐字节相同的 ``{"passed": False, "detail": "mypy 发现 1 处
       问题…"}``——该层从未真正检查过任何代码，且把工具链失败记成代码缺陷。
    2. **假干净**：rc ∉ {0,1} 且输出里没有 ``error:`` / ``note:`` 行时，旧代码
       ``passed = len(error_lines) == 0`` ⇒ ``True``，detail "mypy 发现 0 处
       问题"。实测两条可达路径：mypy 读不到目标文件（rc=2，输出
       ``mypy: can't read file …``）、mypy 被信号杀死（rc=-9，输出为空）。

    现按 rc 语义三态化：0 = 可信报告且零疑点（ok）；1 = 可信报告且有疑点
    （ok）；其余（含 2 致命 / 3 内部错误 / 负数信号 / None）= 未产出可信报告
    ⇒ status=error + fail-closed（passed=False），detail 携带原始输出而不再
    声称"发现 N 处问题"。
    """
    import subprocess
    import tempfile

    if not _layer_enabled("mypy", "TESTLESS_MYPY_ENABLE", "true"):
        return {
            "passed": True,
            "status": VALIDATION_DISABLED,
            "reason": "mypy_layer_disabled",
            "detail": "mypy 层显式关闭（TESTLESS_MYPY_ENABLE=false），跳过",
        }

    try:
        import mypy.api  # noqa: F401  # 探活（缺依赖时降级跳过，不阻断）
    except Exception as exc:  # 装上但坏了（扩展/版本冲突）同样按不可用降级
        logger.warning("mypy 不可用（testless 类型层按 unavailable 降级）: %s", exc)
        # U5（2026-10-05 系统性审查落地）：三态化（缺依赖 ≠ 类型通过）
        return {
            "passed": True,
            "infra_degraded": True,
            "status": VALIDATION_UNAVAILABLE,
            "reason": "mypy_not_installed",
            "detail": "mypy 不可用（未安装或导入失败，ADR-0004 零默认依赖口径），保守跳过",
        }

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(patched_code)
        tmp_path = f.name

    try:
        import subprocess
        import sys

        # 2026-10-11 全面优化批次：run_with_timeout 接线（孤儿风险消除）——
        # mypy 子进程可能派生孙进程；文件后端 + 进程组 kill 保证必然返回，
        # 消除"孙进程持管道写端 → communicate 永久阻塞"挂死风险。
        # 调用点直连 process_utils.run_with_timeout（接线点即 mock 点：
        # 测试 patch("src.utils.process_utils.run_with_timeout")，生产消费
        # 真实实现）；超时口径与历史 TimeoutExpired 逐字归一：
        # - mock 路径：测试直接以 side_effect 抛 TimeoutExpired（历史语义）；
        # - 生产路径：run_with_timeout 超时返回 timed_out=True 不抛异常 →
        #   调用点显式构造 TimeoutExpired 交给同一 except 分支。
        from src.utils.process_utils import run_with_timeout

        result = run_with_timeout(
            [
                # O35（P2）：用当前解释器而非 PATH 上的 "python"——本模块
                # sys_executable() 已为导入冒烟层统一口径，mypy 层此前
                # 硬编码 "python"：venv 场景可能解析到系统解释器（缺 mypy →
                # OSError → 静默"保守跳过"，该层实际从未生效），且跳过原因
                # 只进 detail 文本，调用方无从区分"没装 mypy"与"解释器不对"。
                sys.executable,
                "-m",
                "mypy",
                "--no-error-summary",
                # BH（2026-10-21）：--silent-imports 是 mypy 早已移除的旧拼写，
                # 现代 mypy 只认 --follow-imports=silent；沿用旧拼写会让本层
                # 恒 rc=2 用法错误（见函数 docstring 缺陷 1）。
                "--follow-imports=silent",
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
        if getattr(result, "timed_out", False):
            raise subprocess.TimeoutExpired(cmd="mypy", timeout=60)
        output = (result.stdout + result.stderr).strip()
        # mypy 返回码：0 = 无错误，1 = 有类型错误，2 = 致命错误，3 = 内部错误。
        # 实测补充：目标文件含语法错误时 mypy 亦以 rc=2 报 `error: invalid
        # syntax [syntax]`（它放弃对该文件做类型分析），因此 rc=2 一律按
        # "未产出可信类型报告"处理，原始输出仍进 detail 供人工判读。
        exit_code = result.returncode
        error_lines = [ln for ln in output.splitlines() if "error:" in ln or "note:" in ln]
        if exit_code == 0:
            return {"passed": True, "status": VALIDATION_OK, "detail": "mypy 通过（0 错误）"}
        if exit_code == 1:
            if not error_lines:
                # rc=1 声称有疑点却解析不出任何疑点行 ⇒ 报告不可信，
                # 不能把它读成"0 处问题"（与 BG 轮 pyright_empty_output 同型）。
                return {
                    "passed": False,
                    "status": VALIDATION_ERROR,
                    "reason": "mypy_rc1_no_findings",
                    "detail": f"mypy rc=1 但未解析出疑点行（报告不可信）：{output[-400:] or '（无输出）'}",
                }
            detail = f"mypy 发现 {len(error_lines)} 处问题（前 5 条）：" + "；".join(error_lines[:5])
            return {"passed": False, "status": VALIDATION_OK, "detail": detail}
        return {
            "passed": False,
            "status": VALIDATION_ERROR,
            "reason": f"mypy_rc_{exit_code}",
            "detail": f"mypy 未产出可信报告（rc={exit_code}，本轮无类型证据）：{output[-400:] or '（无输出）'}",
        }
    except (OSError, subprocess.TimeoutExpired) as e:
        # U5（2026-10-05 系统性审查落地）：fail-open 三态化——保持 passed=True
        # 保守跳过语义不变（ADR-0003），但新增 infra_degraded=True 显式区分
        # "mypy 真实通过" 与 "mypy 不可用跳过"（防降级被当稳健统计）。
        # BH：补 status=error（跑了但没产出可信报告）；passed 口径不变——
        # 已披露的降级路径本轮不动，只收口未披露的假干净。
        reason = "mypy_timeout" if isinstance(e, subprocess.TimeoutExpired) else "mypy_exception"
        return {
            "passed": True,
            "infra_degraded": True,
            "status": VALIDATION_ERROR,
            "reason": reason,
            "detail": f"mypy 执行失败（保守跳过，不阻断）: {e}",
        }
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def _run_naming_contract_layer(original_code: str, patched_code: str) -> dict[str, Any]:
    """命名契约回归层（复用 patch_applier.check_naming_contract 的 Python AST 专属实现）。

    BH 轮（2026-10-21）：``check_naming_contract`` 的 ``(True, [])`` 是三件事
    共用的返回值——"比较过且无符号被删"、"原文/补丁不可解析所以没得比"、
    "PATCH_CONTRACT_CHECK=false 恒放行"。旧代码一律渲染成
    "命名契约回归通过（无被删模块级符号）"，实测原文 ``def f(:`` 时该句为
    **假陈述**（从未做过比较）。本轮在 testless 侧前置判别（不改
    patch_applier 的对外契约），把三者分开披露。
    """
    if not _layer_enabled("naming_contract", "TESTLESS_NAMING_CONTRACT_ENABLE", "true"):
        return {
            "passed": True,
            "status": VALIDATION_DISABLED,
            "reason": "naming_contract_layer_disabled",
            "detail": "命名契约层显式关闭（TESTLESS_NAMING_CONTRACT_ENABLE=false），跳过",
        }

    unparseable = _unparseable_side(original_code, patched_code)
    if unparseable is not None:
        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"
        return {
            "passed": False,
            "status": VALIDATION_ERROR,
            "reason": unparseable,
            "detail": f"命名契约回归不可测量（{side}无法解析，未做任何符号比较）",
        }

    if not env_flag("PATCH_CONTRACT_CHECK", True):
        return {
            "passed": True,
            "status": VALIDATION_DISABLED,
            "reason": "patch_contract_check_disabled",
            "detail": "命名契约回归未执行（PATCH_CONTRACT_CHECK=false 恒放行），跳过",
        }

    from src.tools.patch_applier import check_naming_contract

    ok, missing = check_naming_contract(original_code, patched_code)
    if ok:
        return {"passed": True, "status": VALIDATION_OK, "detail": "命名契约回归通过（无被删模块级符号）"}
    return {
        "passed": False,
        "status": VALIDATION_OK,
        "detail": f"命名契约回归失败：缺失符号 {sorted(missing)}",
    }


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
        return {
            "passed": True,
            "status": VALIDATION_DISABLED,
            "reason": "import_smoke_layer_disabled",
            "detail": "导入冒烟层显式关闭（TESTLESS_IMPORT_SMOKE_ENABLE=false），跳过",
        }

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
        # 拒跑是"按设计未执行导入"，不是导入通过的证据：status=disabled
        # （passed 仍为 False，保持既有 fail-closed 拒绝语义）。
        return {
            "passed": False,
            "status": VALIDATION_DISABLED,
            "reason": "refused_dangerous_api",
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
    # 2026-10-11 全面优化批次：run_with_timeout 接线（孤儿风险消除）——
    # 导入冒烟执行的是 LLM 补丁代码，子进程可能派生孙进程；文件后端 +
    # 进程组 kill 保证必然返回，消除"孙进程持管道写端 → communicate
    # 永久阻塞"挂死风险（2026-10-09 批后挂死事故同构面）。
    # 超时口径与历史 TimeoutExpired 逐字归一：
    # - mock 路径：测试以 side_effect=OSError 模拟启动失败（infra_degraded
    #   分支）或 mock 返回 timed_out=True 的 proc（下方构造 TimeoutExpired
    #   → 超时分支）；
    # - 生产路径（run_with_timeout）：超时返回 timed_out=True 不抛异常 →
    #   调用点显式构造 TimeoutExpired 交给同一 except 分支。
    from src.utils.process_utils import run_with_timeout

    try:
        result = run_with_timeout(
            [sys_executable(), "-c", smoke_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
        )
        if getattr(result, "timed_out", False):
            raise subprocess.TimeoutExpired(cmd=smoke_script, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "status": VALIDATION_ERROR,
            "reason": "import_smoke_timeout",
            "detail": f"导入冒烟超时（>{timeout}s）",
        }
    except OSError as e:
        # U5（2026-10-05 系统性审查落地）：三态化（同 mypy 层口径）
        # BH：解释器起不来 ⇒ 本层没跑成，status=unavailable；passed 口径不变。
        return {
            "passed": True,
            "infra_degraded": True,
            "status": VALIDATION_UNAVAILABLE,
            "reason": "import_smoke_exception",
            "detail": f"导入冒烟执行失败（保守跳过，不阻断）: {e}",
        }
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    if result.returncode == 0:
        return {
            "passed": True,
            "status": VALIDATION_OK,
            "detail": f"导入冒烟通过（import {module_name} 成功）",
        }
    tail = (result.stderr or result.stdout or "").strip()[-400:]
    return {
        "passed": False,
        "status": VALIDATION_OK,
        "detail": f"导入冒烟失败（import {module_name} 异常）：{tail or '（无输出）'}",
    }


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
        验证结果 dict：``{"passed": bool, "layers": {...}, "failed_layers":
        [name, ...], "validation_status": str, "degraded_layers": [name, ...]}``。
        **``passed=True`` 只在 ``validation_status == "ok"`` 时才是"四层都验证
        过且无疑点"的证据**；status 为 disabled / unavailable / error 时
        passed=True 仅表示"没有一层报告缺陷"，不表示验证发生过。
    """
    layers: dict[str, dict[str, Any]] = {}
    layers["ast_symbol_guard"] = _run_ast_symbol_guard(original_code, patched_code)
    layers["mypy"] = _run_mypy_layer(patched_code, target_module)
    layers["naming_contract"] = _run_naming_contract_layer(original_code, patched_code)
    layers["import_smoke"] = _run_import_smoke_layer(original_code, patched_code, target_module)

    failed = [name for name, layer in layers.items() if not layer.get("passed", True)]
    overall_passed = len(failed) == 0
    # BH 轮（2026-10-21）：整体可测量性。四层相互独立，故取最差 status
    # （与 BG 轮 type_repair 的"任一后端 ok ⇒ ok"方向相反，见模块常量注释）。
    validation_status = _worst_layer_status(layers)
    degraded = [name for name, layer in layers.items() if layer.get("status", VALIDATION_OK) != VALIDATION_OK]
    result: dict[str, Any] = {
        "passed": overall_passed,
        "layers": layers,
        "failed_layers": failed,
        "validation_status": validation_status,
        "degraded_layers": degraded,
    }
    if degraded:
        # 点名 layer=status:reason，使"passed=True"不会被单独读成验证完成。
        logger.warning(
            "G5 testless 验证可测量性降级（整体 status=%s）：%s",
            validation_status,
            ", ".join(f"{name}={layers[name].get('status')}:{layers[name].get('reason', '-')}" for name in degraded),
        )
    logger.info(
        "G5 testless 验证：%s（失败层: %s；status: %s）",
        "通过" if overall_passed else "未通过",
        ", ".join(failed) if failed else "无",
        validation_status,
    )
    return result


__all__ = [
    "run_testless_validation",
    "sys_executable",
    "testless_validation_enabled",
]
