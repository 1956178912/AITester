# M1（2026-09-29 审查 P0）：假修复/检出三指标 —— 与 passed 历史口径**并行**
# 产出（不改变 passed），供评估层把"测试是否漏检缺陷"与"修复是否真正
# 成功"拆开度量。判分材料来自合成数据集模板自带的 `test_cases`（gold 测试）
# 与 `fixed`（gold 补丁），无需额外 LLM 调用。
#
# 设计原则（保守、零默认行为变化）：
#   1. 三指标对 SWE-bench 任务（metadata["source"] == "swe_bench"）与无
#      gold 材料的任务一律以 None 占位（键集合同构，向后兼容）；
#   2. 指标值 0.0 表示"可测量且为 0"，None 表示"材料缺失/不适用"——
#      下游统计（success_rate 等）不得把 None 计为 0；
#   3. 本模块是**纯函数 + 子进程执行**，不引入 LLM 调用；子进程失败时
#      保守记 None 而非 0（不误报）。
#
# F2P（fail-to-pass）修正（2026-09-30 独立审查 N1，P0）：
#   此前 detection_rate 仅取"生成测试在 buggy 代码上 rc != 0"单边口径，
#   导致"恒失败测试"（assert False / 恒不存在的 import / 语法错误文件）
#   同样记 1.0 —— 完全无信息量的测试获得满分（SWT-Bench 口径要求
#   fail-to-pass 双段：buggy 上红 **且** fixed 上绿，外加收集/语法
#   错误不算检出）。现改为三段判定：
#     F2P = rc_buggy != 0
#           AND rc_fixed == 0
#           AND 无收集/语法错误（"errors during collection" / SyntaxError
#               出现在 buggy 或 fixed 侧任一输出即拒）
#   测试执行错误率（test_error_rate）：生成测试在 buggy 侧以"非 0 但属于
#   收集/语法错误"退出 → 1.0（恒失败测试的直接防线）。

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

# 收集错误 / 语法错误的保守信号（pytest 输出子串，大小写不敏感匹配）。
# 仅取高置信标记，避免把普通断言失败文本误判为"测试执行错误"。
#
# 说明（2026-09-30 独立审查 N1 实测）：
# - pytest 的 import 失败（ModuleNotFoundError）不输出
#   "errors during collection" 字面串（其摘要为 "ERROR collecting
#   ..." + "1 error in ..."，且 rc=2 与断言失败 rc=1 区分）；
# - 语法错误输出 "SyntaxError"（"invalid syntax" 的 E 行）；
# - 因此判据取"rc>=2（收集/编译阶段中断，0 个测试被执行）
#   OR 任一显式标记命中"，双通道互补。
_COLLECTION_ERROR_MARKERS: tuple[str, ...] = (
    "errors during collection",
    "no tests were run",
    "syntaxerror",
    "error in 0.",
)


def _looks_like_test_execution_error(returncode: int, output: str) -> bool:
    """判定一次 pytest 运行是否属于"测试执行错误"（根本没跑起来）。

    双通道判据（任一命中即为执行错误）：
    1. rc >= 2：pytest 约定 rc=1 = 有测试失败（断言级）、rc=0 = 全过；
       rc>=2 表示收集/编译阶段中断（import 失败、语法错误、配置错误
       等），此时没有任何断言被执行，不构成有效 F2P 信号（N1 防线）；
    2. 输出含显式执行错误标记（"errors during collection" /
       "no tests were run" / "SyntaxError" / "error in 0.<s>" 的收集
       阶段中断摘要，如 "1 error in 0.05s"）——兜底 rc 不可得或
       非标准执行器的场景。
    """
    if returncode >= 2:
        return True
    if not output:
        return False
    low = output.lower()
    return any(marker in low for marker in _COLLECTION_ERROR_MARKERS)


def _python_interpreter() -> str:
    """M2（2026-09-30 独立审查 N4，P1）：子进程解释器口径。

    此前硬编码 "python3"：本机 `which python3` 指向系统 Python（如
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3），
    与项目 venv 解释器不同 —— 一旦该解释器无 pytest，所有 M1 任务
    静默退化为 "collection error → detection=1.0 / repair=0.0" 的
    无效口径。现改用 `sys.executable`（本进程解释器，实验脚本与
    _m1_metrics 同进程加载，即 venv 解释器），并在模块加载期做
    前置断言：解释器无 pytest 时直接 raise（fail-fast，不再静默
    退化）。

    环境变量 AITESTER_M1_PYTHON 可显式覆盖（供特殊执行环境使用）。
    """
    override = os.getenv("AITESTER_M1_PYTHON", "").strip()
    interpreter = override or sys.executable
    # 前置断言：解释器必须能 import pytest，否则 M1 指标会整体失效
    probe = subprocess.run(
        [interpreter, "-c", "import pytest"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            f"M1 指标解释器 {interpreter} 无法 import pytest，拒绝产出无效指标：{probe.stderr.strip()[:200]}"
        )
    return interpreter


def _run_pytest_in_tmp(
    test_code: str, target_code: str, module_name: str, timeout: int = 120
) -> tuple[int, str, str] | None:
    """在临时目录里写 target + test 文件并跑 pytest。

    返回 (pytest 退出码, stdout, stderr)；
    - 0 = 全过；非 0 = 存在失败/错误；
    - 超时 / IO 异常 → 返回 None（无法判定，调用方保守记 None）。
    """
    tmpdir = tempfile.mkdtemp(prefix=f"aitester_m1_{module_name}_")
    try:
        target_path = os.path.join(tmpdir, f"{module_name}.py")
        test_path = os.path.join(tmpdir, f"test_{module_name}.py")
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(target_code)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        try:
            res = subprocess.run(
                [
                    _python_interpreter(),
                    "-m",
                    "pytest",
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                    test_path,
                ],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": tmpdir,
                },
            )
            return res.returncode, res.stdout or "", res.stderr or ""
        except subprocess.TimeoutExpired:
            return None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _target_code_after_patch(original_code: str, patch: str) -> str:
    """把系统生成的补丁（unified diff 或完整文件代码）应用到原始代码。

    - 完整文件代码形态（非 unified diff）→ 直接用 patch 文本作为新代码；
    - unified diff 形态 → 用 patch_applier 的安全应用路径（safe_apply_patch）；
    - 应用失败 / 空补丁 → 返回原始代码（口径保守：不假设修复发生）。

    批次 VII（ADR-0021）：完整文件分支先经 normalize_patch_text 清理
    （markdown 围栏 / python 前缀剥离，与写盘链路同口径）。此前直接用
    原始文本——state["patch"] 约定可含围栏残留（E2 存量 274/274 实测
    以 "python\n" 开头），未清理文本首行不可解析，gold 测试 100%
    NameError 失败，repair_rate 被系统性压零（"repair 全线 0"测量伪影，
    清理后重放 51/106 通过）。本修复弥合"透出口径 ≠ 执行口径"分叉；
    干净补丁幂等（清理后不变），历史行为仅在受染输入上改变。
    """
    if not patch or not patch.strip():
        return original_code
    stripped = patch.lstrip()
    if not stripped.startswith(("diff --git", "@@", "---", "+++", "old ", "new ")):
        # 完整文件代码形态（批次 VII：写盘同口径清理，见 docstring）
        from src.tools.patch_applier import normalize_patch_text

        return normalize_patch_text(patch)
    try:
        from src.tools.patch_applier import safe_apply_patch

        new_code, ok = safe_apply_patch(original_code, patch)
        if ok:
            return new_code
    except Exception:
        pass
    return original_code


def _extract_gold_material(task: Any) -> tuple[str, str, str] | None:
    """从任务 metadata 提取 (module_name, gold_test_code, gold_fixed_code)。

    合成数据集（synthetic）：metadata 含 test_cases（gold 测试）与
    fixed（gold 补丁文本，可能是完整函数或 unified diff）；模块名来自
    task_id 最后一段。SWE-bench / 无 gold 材料 → 返回 None。
    """
    md = getattr(task, "metadata", None) or {}
    if md.get("source") == "swe_bench":
        return None
    test_cases = md.get("test_cases") or ""
    fixed = md.get("fixed") or ""
    if not test_cases.strip():
        return None
    # P1-4（2026-10-05 独立审查）：模块名 = task_id 末段。泄漏修复在**生成
    # 层**完成（synthetic_dataset 中性化 task_id 并同步重写 gold import），
    # 本侧派生规则保持不变即自动中性——单点派生，避免双名机制。
    raw_name = str(task.task_id).split("__")[-1]
    module_name = raw_name.replace("-", "_")[:50]
    return module_name, test_cases, fixed


def _gold_fixed_code(task: Any) -> str:
    """gold 修复后的代码全文（F2P 第二段判据）。

    材料来源（合成数据集）：
    - 单文件任务（is_cross_file=False）：metadata["fixed"] 是"修复后的
      函数代码"（完整文件形态或函数体），经 _target_code_after_patch
      应用到 instance_code（空补丁返回原始代码，保守口径）；
    - 跨文件任务（is_cross_file=True）：metadata["fixed_module_code"]
      是被调方修复后的完整模块源码，直接作为固定版代码（该任务
      instance_code = 缺陷方模块全文，"应用"语义无意义，全文替换
      即正确语义）；
    - SWE-bench / 无 gold 材料 → 返回 ""（调用方据此保守降级为 None）。

    注意：noise_seed 注释（实例侧"# noise_seed=<n>"）在固定版侧不存在，
    不影响 gold 测试在固定版上的判定（gold 测试 import 的是模块名，
    与注释无关）。
    """
    md = getattr(task, "metadata", None) or {}
    if md.get("source") == "swe_bench":
        return ""
    original_code = str(getattr(task, "instance_code", "") or "")
    if md.get("is_cross_file"):
        return str(md.get("fixed_module_code") or "")
    fixed = md.get("fixed") or ""
    if not fixed.strip():
        return ""
    return _target_code_after_patch(original_code, fixed)


def _compute_detection_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 检出率（**fail-to-pass 三段判定**，SWT-Bench 口径）。

    定义（2026-09-30 独立审查 N1 修正）：
        1. 生成测试在 original_code（缺陷代码）上运行 → rc_buggy != 0；
        2. 生成测试在 gold 修复代码（fixed）上运行 → rc_fixed == 0；
        3. 两侧输出均无"收集错误 / 语法错误"信号
           （"errors during collection" / "no tests were run" /
             "SyntaxError"）；
        三者同时成立 → detection_rate = 1.0（真实 fail-to-pass 检出）；
        任一不成立 → 0.0。

        特别地，"恒失败测试"（assert False / 恒不存在的 import /
        语法错误文件）在 fixed 上同样非 0 或有收集错误 → 判定 0.0，
        消除 N1 的"坏测试刷满指标"通道。

    无 generated_test / 无 gold 材料 / 执行超时 → None（不可测量，
    不误报）。
    历史 88% 的"假成功"（29/44 iteration-0 无修复动作）在此口径下
    会被如实标为 0.0。

    gold 修复代码缺失时（有 test_cases 但无 fixed 材料）无法完成
    F2P 第二段，保守记 None（不误报，与"无 gold 材料"同口径）。
    """
    if final_state is None:
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, _test_cases, _fixed = mat
    generated_test = final_state.get("generated_test") or ""
    if not generated_test.strip():
        return None
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None

    # F2P 第二段材料：gold 修复代码。缺失时保守 None（不误报，与
    # "无 gold 材料"同口径 —— 无 fixed 材料的任务无法完成 F2P 判定）。
    fixed_code = _gold_fixed_code(task)
    if not fixed_code.strip():
        return None

    rc_buggy = _run_pytest_in_tmp(generated_test, original_code, module_name)
    if rc_buggy is None:
        return None
    buggy_rc, buggy_out, buggy_err = rc_buggy
    rc_fixed = _run_pytest_in_tmp(generated_test, fixed_code, module_name)
    if rc_fixed is None:
        return None
    fixed_rc, fixed_out, fixed_err = rc_fixed

    # 三段判定（N1 修正）
    if buggy_rc == 0:
        return 0.0  # buggy 侧没红 = 缺陷未被检出（盲区通过）
    if _looks_like_test_execution_error(buggy_rc, buggy_out + "\n" + buggy_err):
        return 0.0  # buggy 侧红是"没跑起来"（收集/语法错误），不是检出
    if fixed_rc != 0:
        # fixed 侧仍红：测试恒失败 / 无效（N1 核心防线）；
        # 若 fixed 侧红且属执行错误，同样 0.0（下一分支兜底）
        return 0.0
    if _looks_like_test_execution_error(fixed_rc, fixed_out + "\n" + fixed_err):
        return 0.0  # fixed 侧红且是收集/语法错误 = 测试本身坏
    return 1.0


def _compute_test_error_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 测试执行错误率（N1 防线，2026-09-30 独立审查）：

    定义：生成测试在 buggy 代码上以"非 0 且属于收集/语法错误"退出
    （"errors during collection" / "no tests were run" / "SyntaxError"）
    → 1.0；否则 → 0.0。
    无 generated_test / 无 gold 材料 / 执行超时 → None。

    用途：把"恒失败 / 坏测试"从 detection_rate 的"分母侧"单独报出，
    供统计层直接观测 N1 通道的占比（历史批次 148 个 JSON 无一携带
    本字段，故默认键值 None 保持键集合同构）。
    """
    if final_state is None:
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, _test_cases, _fixed = mat
    generated_test = final_state.get("generated_test") or ""
    if not generated_test.strip():
        return None
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    rc = _run_pytest_in_tmp(generated_test, original_code, module_name)
    if rc is None:
        return None
    rc_val, out, err = rc
    if rc_val != 0 and _looks_like_test_execution_error(rc_val, out + "\n" + err):
        return 1.0
    return 0.0


def _compute_repair_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 修复率（独立裁决）：gold 测试在"应用系统补丁后的代码"上是否全过。

    定义：
        系统生成补丁 → safe_apply_patch(original_code, patch) →
        new_code；再在 new_code 上跑 gold test_cases（模板自带）：
        rc == 0 → repair_rate = 1.0（修复被独立验证）；
        rc != 0 → 0.0（补丁未通过独立裁决）；
        无补丁（iterations=0）→ 0.0（没有修复动作，与历史口径区分）。

    与 passed（"我生成的测试在（可能未修复的）代码上通过"）的区别：
        本指标只看 gold 测试在**最终代码**上的通过性，不依赖 LLM 自写
        测试，消除 oracle-from-implementation 假成功通道。
    """
    if final_state is None:
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    module_name, test_cases, _fixed = mat
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    patch = final_state.get("patch") or ""
    new_code = _target_code_after_patch(original_code, patch)
    rc = _run_pytest_in_tmp(test_cases, new_code, module_name)
    if rc is None:
        return None
    rc_val, _out, _err = rc
    return 1.0 if rc_val == 0 else 0.0


def _compute_false_fix_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 假修复率（任务级布尔）：passed=True 但 gold 独立裁决失败。

    定义：
        passed（历史口径）= True 且 repair_rate = 0.0 → 1.0（假修复）；
        否则 → 0.0。无 gold 材料 / passed 缺失 → None。

    历史主实验（20260925_135638）中 29/44 的"成功"在此指标下会暴露为
    假修复（测试在带缺陷代码上直接通过，代码未改）。
    """
    if final_state is None:
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    passed = bool(final_state.get("test_passed"))
    repair_rate = _compute_repair_rate(task, final_state)
    if repair_rate is None:
        return None
    if passed and repair_rate == 0.0:
        return 1.0
    return 0.0


def _compute_regression_rate(task: Any, final_state: dict[str, Any] | None) -> float | None:
    """M1 回归率（任务级布尔）：补丁应用后 gold P2P 基线测试出现回归。

    定义（R4 独立审查 P0，2026-09-30）：
        系统生成补丁后，gold P2P（pass_to_pass）测试在**应用补丁后的代码**
        上出现"原本全过 → 现失败"的回归 → regression_rate = 1.0；
        否则（无回归 / 无补丁）→ 0.0。
        无 gold 材料 / 无 P2P 材料 / 执行超时 → None（不可测量，不误报）。

    用途：repair_rate 只看"修复是否成功"（F2P 转绿），但修复可能**破坏
    原本正确的行为**（回归）——本指标把"修复引入回归"单独报出，
    供统计层观测"过度修复 / 误删逻辑"通道（与 false_fix_rate 互补：
    假修复是"没修复却通过"，回归是"修复了但破坏其他行为"）。

    材料来源（合成数据集）：metadata["pass_to_pass"] 为 P2P 测试代码列表；
    SWE-bench / 无 P2P 材料 → None。
    """
    if final_state is None:
        return None
    mat = _extract_gold_material(task)
    if mat is None:
        return None
    md = getattr(task, "metadata", None) or {}
    p2p_tests = md.get("pass_to_pass") or []
    if not p2p_tests:
        return None  # 无 P2P 材料，不可测量
    module_name = mat[0]
    original_code = str(getattr(task, "instance_code", "") or "")
    if not original_code.strip():
        return None
    patch = final_state.get("patch") or ""
    new_code = _target_code_after_patch(original_code, patch)
    # P2P 测试代码拼接（列表 → 单个测试文件）
    p2p_code = "\n\n".join(str(t) for t in p2p_tests if str(t).strip())
    if not p2p_code.strip():
        return None
    rc_patched = _run_pytest_in_tmp(p2p_code, new_code, module_name)
    if rc_patched is None:
        return None  # 超时/异常，不可测量
    rc_base = _run_pytest_in_tmp(p2p_code, original_code, module_name)
    if rc_base is None:
        return None
    # 回归 = 基线（原始代码）P2P 全过 且 补丁后 P2P 出现失败
    if rc_base[0] == 0 and rc_patched[0] != 0:
        return 1.0
    return 0.0


def build_m1_task_metrics(task: Any, final_state: dict[str, Any] | None) -> dict[str, Any]:
    """M1 指标集（供 run_benchmark._build_task_result 消费）。

    返回 {"detection_rate": ..., "repair_rate": ..., "false_fix_rate": ...,
    "test_error_rate": ..., "regression_rate": ...,
    "test_regenerated_pass_unverified": ...}。
    键集合同构（历史结果 JSON 结构向后兼容）：无 gold 材料时各指标均
    None；假通过标记仅 passed=True 且 regeneration_count > 0 时 True，
    否则 None。

    2026-09-30 独立审查 N1：新增 test_error_rate（测试执行错误率，
    坏测试直接防线）；detection_rate 改 F2P 三段判定。
    2026-09-30 独立审查 R4：新增 regression_rate（修复引入回归观测）。
    """
    detection_rate: float | None = None
    repair_rate: float | None = None
    false_fix_rate: float | None = None
    test_error_rate: float | None = None
    regression_rate: float | None = None
    if final_state is not None:
        detection_rate = _compute_detection_rate(task, final_state)
        repair_rate = _compute_repair_rate(task, final_state)
        false_fix_rate = _compute_false_fix_rate(task, final_state)
        test_error_rate = _compute_test_error_rate(task, final_state)
        regression_rate = _compute_regression_rate(task, final_state)
    test_regenerated_pass_unverified: bool | None = None
    if (
        final_state is not None
        and bool(final_state.get("test_passed"))
        and int(final_state.get("regeneration_count", 0)) > 0
    ):
        test_regenerated_pass_unverified = True
    return {
        "detection_rate": detection_rate,
        "repair_rate": repair_rate,
        "false_fix_rate": false_fix_rate,
        "test_error_rate": test_error_rate,
        "regression_rate": regression_rate,
        "test_regenerated_pass_unverified": test_regenerated_pass_unverified,
    }
