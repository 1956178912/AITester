"""
测试执行器基础设施：子进程运行、超时重试与临时资源清理。

拆分自 executor.py（结构优化轮次）：ExecutorAgent 的类主体保留在
executor.py，本模块承载三条执行链路共用的底层能力——
带重试的 pytest 子进程执行（_run_pytest_with_retry）与临时文件/沙箱目录清理
（_cleanup_temp_file / _cleanup_sandbox）。
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def run_pytest_with_retry(self, cmd: list, env: dict, project_root: str) -> tuple[str, Any]:
    """
    带重试的 pytest 执行逻辑，最多尝试 2 次。
    超时/环境问题直接返回 EARLY_RETURN 标记，其他异常仅记录日志并返回空结果。

    由 ExecutorAgent 实例调用（self.timeout 为单次超时秒数）。

    Returns:
        (output, last_result) 元组：last_result 为 subprocess.CompletedProcess、
        ("EARLY_RETURN", error_info) 标记元组或 None。
    """
    max_attempts = 2
    last_output = ""
    last_result = None

    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=project_root,
                env=env,
            )
            last_result = result
            last_output = result.stdout + result.stderr
            if result.returncode == 0:
                break
            logger.warning("第 %d 次执行失败，尝试重试...", attempt + 1)
        except subprocess.TimeoutExpired as e:
            # TimeoutExpired 携带超时前已累积的部分 stdout/stderr（text 模式下为 str，
            # 未产生时可能为 None）。合并进 last_output，让下游 Debugger 能拿到现场
            # 快照而非空白文本（此前超时分支丢失了部分输出）。
            partial_output = (e.output or "") + (e.stderr or "")
            last_output = partial_output
            error_msg = f"测试执行超时（>{self.timeout}s）"
            logger.error("测试执行超时（>%ds）: %s", self.timeout, e)
            error_info = {
                "type": "timeout",
                "message": error_msg,
                "timeout_seconds": self.timeout,
                "command": " ".join(cmd[:5]) if len(cmd) > 5 else " ".join(cmd),
            }
            # 超时/环境错误需由调用方直接 return，这里用特殊标记
            return last_output, ("EARLY_RETURN", error_info)
        except FileNotFoundError as e:
            error_msg = "执行环境错误（找不到 pytest 或 Python 解释器）"
            logger.error("执行环境错误（找不到 pytest）: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "file_not_found",
                    "message": error_msg,
                    "detail": str(e),
                },
            )
        except PermissionError as e:
            error_msg = "权限不足，无法执行测试文件"
            logger.error("权限错误: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "permission_error",
                    "message": error_msg,
                    "file_path": str(e.filename) if hasattr(e, "filename") else "",
                },
            )
        except Exception as e:
            error_msg = f"测试执行异常: {type(e).__name__}: {e}"
            logger.error("测试执行异常: %s", e)
            last_output = error_msg
            last_result = None
            break

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
