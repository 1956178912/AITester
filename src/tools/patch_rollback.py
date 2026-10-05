"""A-03（2026-10-04 系统审查 P0）：补丁应用前快照 + P2P 全量回归 + 失败自动回滚协议。

背景（§7 建议 A-03）：
    单文件场景此前只有"应用后语法校验 + 命名契约守卫 + 危险 API 守卫"
    （safe_apply_patch / safe_apply_patch_contract，均不回归执行），缺
    "应用前快照 → 应用后 P2P 全量回归 → 回归失败自动回滚快照"协议。
    跨文件分支已有拓扑序整体回滚（cross_file.apply_multi_file_patch），
    但单文件是主实验高频路径——坏补丁一旦应用即污染 target_code，
    带着错误诊断进入下一轮迭代（multi_candidate 注释自述的"一步走错
    步步错"风险），且 M1 repair_rate 的保守 None 口径在无 gold 时
    无法裁决"修复是否真的没破坏原有行为"。

本模块（纯静态协议 + 可选子进程回归，零默认行为变化）：
    1. **快照**（snapshot / restore）：对"被测代码 + 测试代码"做内容级
       快照（dict 语义，不落盘——与 executor 临时目录生命周期一致；
       需要落盘审计时经 save_snapshot_json 显式导出，非默认）；
    2. **P2P 全量回归裁决**（run_p2p_regression）：对"应用补丁后的代码"
       跑独立测试套件（pass-to-pass 口径：补丁前全过的测试，补丁后
       必须仍全过；任一失败 → 判定"过度修复/误删逻辑" → 自动回滚）；
       回归执行器默认走子进程 pytest（与 _m1_metrics._run_pytest_in_tmp
       同口径，隔离 + 超时），无 gold/测试材料时保守返回"不可裁决"
       （verdict="no_oracle"，不静默放行、不静默拒绝）；
    3. **回滚**（PatchRollbackProtocol.run）：快照 → 应用 → P2P →
       失败则 restore（返回 snapshot 原内容 + verdict 标注），成功则
       保留补丁并标注回归证据（verdict="verified" / "no_oracle"）。

设计口径（与 ADR-0003 一致：默认关，独立开关）：
    - PATCH_SNAPSHOT_ROLLBACK_ENABLE=true 时启用（默认 false，历史口径
      零变化）；_patch_applier_node 在启用时调用本协议（未启用时
      走原 safe_apply_patch 路径逐字节不变）；
    - 回归失败"自动回滚"仅回滚**内容**（target_code 恢复快照值），
      不撤销已发生的 LLM 调用 / 不删除已落盘工件（保守：工件是
      实验证据，回滚语义限于"代码状态"，避免二次污染实验记录）；
    - P2P 回归的"独立测试套件"来源优先级：
      (a) 显式传入的 test_code（gold 测试 / 生成测试）；
      (b) 无 test_code → verdict="no_oracle"（不臆测测试，保守不裁决，
        但补丁仍允许应用——由 M1 repair_rate 的 None 口径兜底）。

工具/命令（验证协议落地）：
    pytest tests/test_patch_rollback.py
    PATCH_SNAPSHOT_ROLLBACK_ENABLE=true python experiments/run_benchmark.py --dataset synthetic --task-count 5
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

_ENV_ENABLE = "PATCH_SNAPSHOT_ROLLBACK_ENABLE"
# P2P 回归子进程超时（秒）：与 executor 的 LLM_TIMEOUT 解耦——回归只跑
# 测试、不跑 LLM，默认 60s 足够（大测试套件场景可经 env 上调）
_ENV_P2P_TIMEOUT = "PATCH_P2P_TIMEOUT"
_DEFAULT_P2P_TIMEOUT = 60
# R4b（2026-10-05 审查 P0）：fail-closed 口径开关（默认 false 保持历史行为）。
# 历史口径：rc>=2（收集/语法错误）/ 超时 / IO 异常 → verdict="regression_error"
# 且**保留补丁**（防"测试自身坏 → 误杀好补丁"，与 _m1_metrics 的
# test_error_rate 同源保守口径）。
# 开启 fail-closed 后：上述异常口径一律按 regression_failed 处理（触发自动
# 回滚）——"回归无法裁决 = 不能证明补丁安全 = 回滚"的保守立场，适用于
# 补丁写盘风险敏感场景（如生产目标 / 长实验主批次）。坏测试误杀风险由
# 证据门（patch_evidence）与 M1 None 口径在下游兜底。
_ENV_FAIL_CLOSED = "PATCH_ROLLBACK_FAIL_CLOSED"


def rollback_fail_closed_enabled() -> bool:
    """R4b fail-closed 口径开关（PATCH_ROLLBACK_FAIL_CLOSED=true 时启用，默认 false）。

    默认关闭：rc>=2 / 超时 / IO 异常归 regression_error 且保留补丁（历史
    口径）；开启后这些口径改判 regression_failed 触发自动回滚。
    """
    return os.getenv(_ENV_FAIL_CLOSED, "false").lower() in ("true", "1", "on")


def snapshot_rollback_enabled() -> bool:
    """A-03 快照/回滚协议开关（PATCH_SNAPSHOT_ROLLBACK_ENABLE=true 时启用，默认 false）。

    默认关闭：_patch_applier_node 在开关关时走原 safe_apply_patch 路径
    （逐字节历史口径）；开启时走 run() 协议（快照 + P2P + 自动回滚）。
    与 ADR-0003"新能力独立开关、默认行为不变"口径一致。
    """
    return os.getenv(_ENV_ENABLE, "false").lower() in ("true", "1", "on")


def _p2p_timeout() -> int:
    try:
        return int(os.getenv(_ENV_P2P_TIMEOUT, str(_DEFAULT_P2P_TIMEOUT)))
    except ValueError:
        return _DEFAULT_P2P_TIMEOUT


# ─── 1. 快照层（内容级，dict 语义）─────────────────────────────────────────


def snapshot(target_code: str, test_code: str = "") -> dict[str, str]:
    """对（被测代码，测试代码）做内容级快照（纯数据，零 IO）。

    Args:
        target_code: 被测代码原文（补丁应用前）。
        test_code: 测试代码（P2P 回归用；空串 = 无测试材料）。

    Returns:
        {"target_code": str, "test_code": str, "snapshot_id": str}
        snapshot_id 为内容哈希（sha256 前 12 位），供日志/工件引用
        （不落盘——落盘审计走 save_snapshot_json 显式导出）。
    """
    import hashlib

    material = (target_code or "") + "\x00" + (test_code or "")
    return {
        "target_code": target_code or "",
        "test_code": test_code or "",
        "snapshot_id": hashlib.sha256(material.encode("utf-8")).hexdigest()[:12],
    }


def restore(snap: dict[str, str]) -> tuple[str, str]:
    """从快照恢复（被测代码，测试代码）原内容（快照的逆操作）。"""
    return snap.get("target_code", ""), snap.get("test_code", "")


def save_snapshot_json(snap: dict[str, str], path: str) -> str:
    """把快照导出为 JSON 文件（显式审计用；默认协议不落盘）。

    原子写（临时文件 + rename），与 LLM 文件缓存的原子替换口径一致
    （防半写文件）。返回写入的绝对路径。
    """
    import pathlib

    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return str(p.resolve())


# ─── 2. P2P 全量回归裁决（子进程 pytest，与 _m1_metrics 同口径）──────────


def run_p2p_regression(
    patched_target_code: str,
    test_code: str,
    module_name: str,
    timeout: int | None = None,
    fail_closed: bool | None = None,
) -> dict[str, Any]:
    """对"应用补丁后的代码"跑独立测试套件（pass-to-pass 全量回归）。

    口径（保守）：
    - test_code 为空 → verdict="no_oracle"（无测试材料不臆测，补丁是否
      保留由调用方 M1 repair_rate 的 None 口径兜底，本层不裁决）；
    - 子进程 pytest 全过 → verdict="verified"（回归证据：rc=0）；
    - 子进程 pytest 有失败 → verdict="regression_failed"（自动回滚触发）；
    - 子进程收集/语法错误（rc>=2 / "no tests were run"）→
      verdict="regression_error"（测试本身坏，不计入"修复破坏"，
      调用方按 no_oracle 处理——与 _m1_metrics 的 test_error_rate 同源
      保守口径，防坏测试误触发回滚）。
    - R4b（2026-10-05）：fail_closed=True（或 env PATCH_ROLLBACK_FAIL_CLOSED=true）
      时，上一条的"收集错误 / 超时 / IO 异常"口径一律改判
      regression_failed（触发回滚）——"回归无法裁决 = 不能证明补丁安全
      = 回滚"。fail_closed=None 时读环境开关（默认 false 历史口径）。

    Returns:
        {"verdict": str, "returncode": int | None, "output_tail": str}
    """
    if fail_closed is None:
        fail_closed = rollback_fail_closed_enabled()
    if not test_code or not test_code.strip():
        return {"verdict": "no_oracle", "returncode": None, "output_tail": ""}

    out_timeout = timeout if timeout is not None else _p2p_timeout()
    tmpdir = tempfile.mkdtemp(prefix="aitester_p2p_")
    try:
        module_path = os.path.join(tmpdir, f"{module_name}.py")
        test_path = os.path.join(tmpdir, f"test_{module_name}_p2p.py")
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(patched_target_code)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-p", "no:cacheprovider", "--tb=line", "-q"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=out_timeout,
                check=False,
            )
            rc = proc.returncode
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            # R4b：fail-closed 时超时也回滚（回归无法裁决 ≠ 补丁安全）
            verdict = "regression_failed" if fail_closed else "regression_error"
            return {
                "verdict": verdict,
                "returncode": None,
                "output_tail": f"p2p timeout after {out_timeout}s",
            }
        # rc>=2 = 收集/编译阶段中断（import 失败 / 语法错误 / 无测试）→
        # 与 _m1_metrics._looks_like_test_execution_error 同口径归
        # regression_error（坏测试不触发回滚，防"测试自身坏 → 误杀好补丁"）；
        # R4b fail-closed 时改判 regression_failed（回滚）
        low = output.lower()
        if (rc is not None and rc >= 2) or "no tests were run" in low:
            verdict = "regression_failed" if fail_closed else "regression_error"
            return {"verdict": verdict, "returncode": rc, "output_tail": output[-500:]}
        if rc == 0:
            return {"verdict": "verified", "returncode": 0, "output_tail": output[-500:]}
        # rc == 1 = 存在测试失败（断言级）→ 回归未过 → 触发自动回滚
        return {"verdict": "regression_failed", "returncode": rc, "output_tail": output[-500:]}
    except OSError as e:
        # IO 异常（磁盘满 / 权限）→ 保守 no_oracle（不静默放行，也不误杀）；
        # R4b fail-closed 时改判 regression_failed（回滚）
        logger.warning("A-03 P2P 回归 IO 异常（fail_closed=%s）：%s", fail_closed, e)
        verdict = "regression_failed" if fail_closed else "regression_error"
        return {"verdict": verdict, "returncode": None, "output_tail": str(e)[:500]}
    finally:
        _cleanup_tmpdir(tmpdir)


def _cleanup_tmpdir(tmpdir: str) -> None:
    import shutil

    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except OSError:
        logger.debug("A-03 P2P 临时目录清理失败（ignore_errors）：%s", tmpdir)


# ─── 3. 回滚协议（快照 → 应用 → P2P → 失败回滚）────────────────────────────


class PatchRollbackProtocol:
    """A-03 快照/回滚协议对象（供 _patch_applier_node 接线；纯静态方法）。

    用法：
        pr = PatchRollbackProtocol()
        result = pr.run(
            original_code, patch, test_code, module_name,
            apply_fn=safe_apply_patch,   # 注入应用函数（默认 safe_apply_patch）
        )
        # result["applied_code"] / result["verdict"] / result["rolled_back"]
    """

    def run(
        self,
        original_code: str,
        patch: str,
        test_code: str = "",
        module_name: str = "",
        apply_fn: Any | None = None,
        fail_closed: bool | None = None,
    ) -> dict[str, Any]:
        """快照 → 应用补丁 → P2P 回归 → 失败自动回滚（单文件协议）。

        Args:
            original_code: 补丁应用前的被测代码。
            patch: LLM 生成的补丁代码。
            test_code: P2P 回归用独立测试套件（gold / 生成测试；空 = 无 oracle）。
            module_name: 被测模块名（P2P 子进程写盘用）。
            apply_fn: 补丁应用函数（默认 None = 延迟 import safe_apply_patch，
                避免模块级循环依赖；测试可注入 stub 验证回滚路径）。
            fail_closed: R4b fail-closed 口径（None = 读环境开关
                PATCH_ROLLBACK_FAIL_CLOSED，默认 false 历史口径）。

        Returns:
            {
              "applied_code": str,      # 最终保留的代码（回滚后 = original_code）
              "success": bool,           # 补丁是否被保留（regression_failed → False）
              "verdict": str,           # verified / regression_failed / no_oracle /
                                        #   regression_error / apply_failed
              "rolled_back": bool,      # 是否触发了自动回滚
              "snapshot_id": str,       # 快照引用（日志/工件关联）
              "p2p_returncode": int | None,
            }
        """
        if apply_fn is None:
            from src.tools.patch_applier import safe_apply_patch

            apply_fn = safe_apply_patch

        snap = snapshot(original_code, test_code)
        new_code, apply_ok = apply_fn(original_code, patch)
        if not apply_ok:
            # 应用本身失败（语法/契约/危险 API）→ safe_apply_patch 已回滚
            # 到 original_code（其语义），本层直接标注 verdict，不二次回滚
            return {
                "applied_code": original_code,
                "success": False,
                "verdict": "apply_failed",
                "rolled_back": True,
                "snapshot_id": snap["snapshot_id"],
                "p2p_returncode": None,
            }

        # 应用成功 → P2P 全量回归裁决（fail_closed 透传，R4b）
        p2p = run_p2p_regression(new_code, test_code, module_name or "module_under_test", fail_closed=fail_closed)
        verdict = p2p["verdict"]
        if verdict == "regression_failed":
            # 回归未过 → 自动回滚到快照（内容级 restore）
            restored_code, _ = restore(snap)
            logger.warning(
                "A-03 P2P 回归失败（rc=%s），自动回滚补丁（snapshot=%s）",
                p2p.get("returncode"),
                snap["snapshot_id"],
            )
            return {
                "applied_code": restored_code,
                "success": False,
                "verdict": verdict,
                "rolled_back": True,
                "snapshot_id": snap["snapshot_id"],
                "p2p_returncode": p2p.get("returncode"),
            }
        # verified / no_oracle / regression_error → 保留补丁（regression_error
        # 保守保留：坏测试不误杀好补丁，由 M1 的 None 口径兜底裁决）
        return {
            "applied_code": new_code,
            "success": verdict in ("verified", "no_oracle", "regression_error"),
            "verdict": verdict,
            "rolled_back": False,
            "snapshot_id": snap["snapshot_id"],
            "p2p_returncode": p2p.get("returncode"),
        }


__all__ = [
    "PatchRollbackProtocol",
    "restore",
    "rollback_fail_closed_enabled",
    "run_p2p_regression",
    "save_snapshot_json",
    "snapshot",
    "snapshot_rollback_enabled",
]
