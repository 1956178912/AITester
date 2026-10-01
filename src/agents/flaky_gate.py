"""
R35/R31（2026-09-30 独立审查 P0）：flaky 测试门禁（重复执行一致性检测）。

背景（ICSE-SEIP 2026：63% flaky 来自无序集合）：
    LLM 生成的测试可能因**非确定性**（dict/set 迭代顺序、时间、随机数、
    并发）而"同代码多次执行结果不一致"——flaky 测试既制造假失败
    （本应通过却偶尔失败 → 误判"代码有缺陷"）也制造假成功
    （本应失败却偶尔通过 → 误判"修复正确"），污染 M1 三指标。
    本模块提供**纯数据**的 flaky 检测口径（零 LLM 成本）：
    对同一 (target_code, generated_test) 重复执行 N 次（默认 3，
    稳定性口径 30），若 N 次结果不一致（既有 pass 又有 fail）→
    标记 flaky=True，统计层按"不可信"剔除/单列，不计入 success/failure。

设计口径（保守、纯数据、默认关、不改变单次执行行为）：
    - FLAKY_CHECK_ENABLE=false（默认）时本模块零行为变化；
    - 开启后，_executor_node 对**失败轮**做额外重复执行（passed 轮
      无需重测——全绿即稳定），重复次数 FLAKY_REPEAT_COUNT（默认 3，
      稳定性用 30）；
    - flaky=True 时把 test_passed 保守记为 False（失败口径：既有
      成功又有失败说明测试本身不稳定，不能作为"修复正确"证据），
      并写入 state["flaky_detected"] / state["flaky_pass_count"] /
      state["flaky_total_count"]（供统计层"flaky fraction"消费）；
    - 重复执行全部复用同一 ExecutorAgent 实例（同沙箱/v 环境），
      仅重跑 pytest 子进程（缓存命中下 LLM 零成本，纯 subprocess）。

消费方式（纯观测层 + 保守路由）：
    - 实验统计：flaky fraction（flaky 任务占比）入工件；
    - M1 指标：flaky 任务的 detection/repair 按"不可测"处理
      （None），避免 flaky 假信号污染三指标。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_ENABLE = "FLAKY_CHECK_ENABLE"
_ENV_REPEAT = "FLAKY_REPEAT_COUNT"
_DEFAULT_REPEAT = 3


def flaky_check_enabled() -> bool:
    """R35/R31 flaky 门禁开关（FLAKY_CHECK_ENABLE=true 时启用，默认 false 保持历史口径）。"""
    return os.getenv(_ENV_ENABLE, "false").lower() in ("true", "1", "on")


def flaky_repeat_count() -> int:
    """重复执行次数（FLAKY_REPEAT_COUNT，默认 3；稳定性口径设 30）。"""
    try:
        return max(2, int(os.getenv(_ENV_REPEAT, str(_DEFAULT_REPEAT))))
    except ValueError:
        return _DEFAULT_REPEAT


def classify_flaky(results: list[bool]) -> dict[str, Any]:
    """对 N 次重复执行的结果列表做 flaky 分类（纯数据，零 LLM 成本）。

    Args:
        results: 每次执行的 passed 布尔值列表（按执行顺序）。

    Returns:
        {"flaky": bool, "pass_count": int, "fail_count": int, "total": int}
        - flaky = 既有 pass 又有 fail（结果不一致）；
        - 全 pass / 全 fail → flaky=False（稳定，结果可信）。
        空列表 → flaky=False（无可判数据，保守）。
    """
    total = len(results)
    if total == 0:
        return {"flaky": False, "pass_count": 0, "fail_count": 0, "total": 0}
    pass_count = sum(1 for r in results if r)
    fail_count = total - pass_count
    return {
        "flaky": pass_count > 0 and fail_count > 0,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total": total,
    }


def detect_flaky(
    executor: Any,
    test_code: str,
    target_file: str,
    target_function: str | None,
    base_result: dict[str, Any],
) -> dict[str, Any]:
    """对已失败的一次执行结果做重复执行 flaky 检测（仅失败轮触发，省成本）。

    Args:
        executor: ExecutorAgent 实例（复用同一沙箱/v 环境配置）。
        test_code / target_file / target_function: 与被测轮相同的执行参数。
        base_result: 首轮执行的完整结果 dict（含 passed / output /
            coverage / failed_cases / error_info）。

    Returns:
        {"flaky": bool, "pass_count": int, "fail_count": int, "total": int,
         "results": [bool, ...]}
        重复执行异常时保守降级（flaky=False，results 仅含首轮），不阻断主流程。
    """
    repeat = flaky_repeat_count()
    results: list[bool] = [bool(base_result.get("passed"))]
    for _ in range(repeat):
        try:
            r = executor.execute(test_code, target_file, target_function)
            results.append(bool(r.get("passed")))
        except Exception as e:  # 重复执行失败：保守，不阻断
            logger.debug("R35 flaky 重复执行异常（保守降级，不阻断）: %s", e)
            break
    cls = classify_flaky(results)
    cls["results"] = results
    return cls


__all__ = [
    "classify_flaky",
    "detect_flaky",
    "flaky_check_enabled",
    "flaky_repeat_count",
]
