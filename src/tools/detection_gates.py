"""检出优先协议双门（AC2，2026-10-06 第十轮审查 T-P0-4）。

背景（R-P0-2 生死实验合并报告"已知口径缺口"节的机制归因）：
- 88 行 red_not_repaired 但 detection=0 —— **过红测试**通道：测试在
  buggy 上红、在 gold fixed 上也红（F2P 三段不通过，非缺陷特异），
  却被路由进修复循环空耗迭代；
- 28 行 red_then_green 但 detection=0 —— **修复循环抹红**通道：修复
  过程中再生成测试，最终测试在 buggy 原码上变绿（检出证据被销毁，
  经典 oracle-from-implementation 假成功通道）。

双门（均默认关，ADR-0003 口径；logic 档经 _PROFILE_PRESETS 注入，
为检出优先协议 ADR-0015 的扩展）：
1. 特异性门（DETECTION_SPECIFICITY_GATE_ENABLE）：首轮红后，把当前
   生成测试在 gold fixed 代码上执行——转绿 = 缺陷特异红（放行进修复
   循环）；仍红 = 过红（路由 regenerate 换缺陷特异的测试，见
   workflow._should_debug 的 specificity_gate_over_red 分支）。
2. 红回归门（RED_REGRESSION_GATE_ENABLE）：曾见红、测试被再生成且
   当前变绿、而源码未被修补时——红证人被"换测试"抹掉（假成功），
   恢复红证人测试并保守交回修复循环（纯状态比较，零额外执行）。

执行委托说明：门①的对照执行复用 experiments/_m1_metrics._run_pytest_in_tmp
（与 M1 事后裁决完全同一原语，行为口径一致，不新增第二套子进程执行面）。
graph→experiments 的函数内延迟导入沿 mutation_advisor.py / nodes.py
既有先例，架构债在 ADR-0016 登记（后续收敛为 src 层统一执行原语）。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

# module_name 安全校验：只允许 Python 标识符（字母/数字/下划线，首字符
# 非数字）。module_name 同时进入委托原语的临时目录文件名（f"{name}.py"）
# 与测试的 import 目标——**必须在委托前**于本层校验（M1 原语自身不做
# 该校验，名字携带路径分隔符时会拼出临时目录外的路径）。非标识符 →
# unavailable（门降级，走历史路由），绝不放行到委托层。
_SAFE_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 环境变量名以 _ENV 前缀常量声明（scripts/gates/check_env_budget.py 的静态
# 扫描口径：os.getenv("字面量") 与模块级 _ENV* = "字面量" 两种模式，
# 间接常量须走 _ENV 前缀才被识别）。
_ENV_SPECIFICITY_GATE = "DETECTION_SPECIFICITY_GATE_ENABLE"
_ENV_RED_REGRESSION_GATE = "RED_REGRESSION_GATE_ENABLE"

# 门①对照执行超时（秒）：与 M1 判定同量级；超时/不可用一律按
# "unavailable" 保守放行（fail-open 到历史路由，门是增强不是阻断点）。
_GATE_TIMEOUT_SECONDS = 60


def detection_specificity_gate_enabled() -> bool:
    """特异性门开关（DETECTION_SPECIFICITY_GATE_ENABLE，默认 false）。

    读取口径：函数调用时读 env（非 import 期常量），便于测试 monkeypatch
    与 logic 档 setdefault 注入（与 config.detection_first_enabled 同口径）。
    """
    return os.getenv(_ENV_SPECIFICITY_GATE, "false").lower() in ("true", "1", "on")


def red_regression_gate_enabled() -> bool:
    """红回归门开关（RED_REGRESSION_GATE_ENABLE，默认 false）。"""
    return os.getenv(_ENV_RED_REGRESSION_GATE, "false").lower() in ("true", "1", "on")


def _run_test_against_code(
    test_code: str,
    target_code: str,
    module_name: str | None,
    timeout: int = _GATE_TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """委托 M1 既有原语执行（test 对 target_code），失败返回 None。

    experiments._m1_metrics._run_pytest_in_tmp 与 M1 detection 裁决共用，
    语义：rc==0 = 全过（绿）；非 0 = 红；None = 超时 / IO 异常 / 材料
    缺失 / module_name 非法（不可判定）。任何导入/执行异常均吞掉并
    返回 None（门降级为 unavailable，不阻断主流程）。
    """
    if not module_name or not _SAFE_MODULE_RE.match(module_name):
        return None
    try:
        from experiments._m1_metrics import _run_pytest_in_tmp as _runner

        res = _runner(test_code, target_code, module_name, timeout=timeout)
    except Exception:
        logger.warning("AC2 门执行原语不可用（experiments._m1_metrics 委托失败），保守放行", exc_info=True)
        return None
    if res is None:
        return None
    return {"green": res[0] == 0, "rc": res[0], "unavailable": False}


def specificity_verdict(
    test_code: str,
    gold_fixed_code: str | None,
    module_name: str | None,
) -> str:
    """门①判定：当前红测试是否缺陷特异。

    Args:
        test_code: 当前生成测试全文。
        gold_fixed_code: gold 修复代码全文（state["gold_fixed_code"]，
            合成任务由 run_benchmark 从任务材料管道注入；None / 空串 =
            无 gold 材料——真实仓库场景，后续批次以变异体裁决替代）。
        module_name: 目标模块名。

    Returns:
        - "specific_red"：gold fixed 上转绿（buggy 红 + fixed 绿，缺陷特异）；
        - "over_red"：gold fixed 上仍红（过红，F2P 三段不通过）；
        - "unavailable"：无 gold 材料 / 执行不可判定（保守放行，走历史
          路由进修复循环）。
    """
    if not gold_fixed_code or not gold_fixed_code.strip() or not (test_code and test_code.strip()):
        return "unavailable"
    res = _run_test_against_code(test_code, gold_fixed_code, module_name)
    if res is None or res.get("unavailable"):
        return "unavailable"
    return "specific_red" if res["green"] else "over_red"


def red_regression_check(state: Mapping[str, Any], current_test: str) -> dict[str, Any] | None:
    """门②判定（纯状态比较，零执行）：再生成是否抹掉了既有红证人。

    判定条件（全部满足才判"抹红"）：
    - 红回归门开启；
    - 本任务曾见红（detection_first_red_seen=True）且存在红证人快照
      （red_witness_test_code，iteration==0 首轮红时由 executor 写入）；
    - 当前测试与红证人不同（= 测试被再生成替换过，regeneration_count>0）；
    - 源码未被修补（state["target_code"] == state["original_target_code"]）
      ——已落地补丁的场景交 M1 事后独立裁决（gold 裁决口径），门内
      不重复执行。

    Args:
        state: 当前工作流状态（只读）。
        current_test: 当前生成测试全文。

    Returns:
        违规时的状态更新片段
        {"red_regression_violation": True, "generated_test": <红证人>,
         "test_passed": False}
        （恢复红证人测试 + 保守置失败，交回修复循环走"修源码"而非
        "换测试"通道）；无违规 / 门未开 / 材料不足时 None（零行为变化）。
    """
    if not red_regression_gate_enabled():
        return None
    if not state.get("detection_first_red_seen"):
        return None
    witness = state.get("red_witness_test_code")
    if not witness or current_test == witness:
        return None
    if int(state.get("regeneration_count", 0) or 0) <= 0:
        return None
    if state.get("target_code") != state.get("original_target_code"):
        return None
    return {
        "red_regression_violation": True,
        "generated_test": witness,
        "test_passed": False,
    }


__all__ = [
    "detection_specificity_gate_enabled",
    "red_regression_check",
    "red_regression_gate_enabled",
    "specificity_verdict",
]
