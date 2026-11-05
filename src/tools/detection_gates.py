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
import re
from collections.abc import Mapping
from typing import Any

from src.utils.env_utils import env_flag
from src.utils.pytest_output import pytest_summary_counts, suite_has_effective_pass

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
    return env_flag(_ENV_SPECIFICITY_GATE)


def red_regression_gate_enabled() -> bool:
    """红回归门开关（RED_REGRESSION_GATE_ENABLE，默认 false）。"""
    return env_flag(_ENV_RED_REGRESSION_GATE)


def _pytest_in_tmp_raw(
    test_code: str,
    target_code: str,
    module_name: str | None,
    timeout: int,
    task_metadata: dict[str, Any] | None,
) -> tuple[int, str, str] | None:
    """单次委托 M1 执行原语；不可执行（module_name 非法 / 委托异常）→ None。

    `_run_test_against_code`（AC2 双门）与 `run_official_tests`（B1 gold 裁决）
    共用同一份"执行物理"：module_name 同时进入委托原语的临时目录文件名与
    测试的 import 目标，**必须在委托前**于本层校验；委托异常一律吞掉记
    None（调用方按不可判定降级，不阻断主流程）。
    """
    if not module_name or not _SAFE_MODULE_RE.match(module_name):
        return None
    try:
        from experiments._m1_metrics import _run_pytest_in_tmp as _runner

        return _runner(test_code, target_code, module_name, timeout=timeout, task_metadata=task_metadata)
    except Exception:
        logger.warning("AC2 门执行原语不可用（experiments._m1_metrics 委托失败），保守放行", exc_info=True)
        return None


def _run_test_against_code(
    test_code: str,
    target_code: str,
    module_name: str | None,
    timeout: int = _GATE_TIMEOUT_SECONDS,
    task_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """委托 M1 既有原语执行（test 对 target_code），失败返回 None。

    experiments._m1_metrics._run_pytest_in_tmp 与 M1 detection 裁决共用，
    语义：rc==0 = 全过（绿）；非 0 = 红；None = 超时 / IO 异常 / 材料
    缺失 / module_name 非法（不可判定）。任何导入/执行异常均吞掉并
    返回 None（门降级为 unavailable，不阻断主流程）。需要逐类理由与
    摘要计数的三值裁决（gold）走 `run_official_tests`。

    task_metadata：与 M1 事后裁决同口径透传（P0-1，2026-10-11 全面优化
    批次：跨文件任务必传——否则委托层走单文件物化，伴生模块缺失
    导致 rc>=2 被误判 over_red；未传时行为与历史逐位一致，零回归）。
    """
    res = _pytest_in_tmp_raw(test_code, target_code, module_name, timeout, task_metadata)
    if res is None:
        return None
    # P0-1（2026-10-11 全面优化批次）：复用 M1 既有的执行错误判据——
    # rc>=2 / 收集错误 = "根本没跑起来"，与 M1 的 detection 三态（None
    # 而非 0.0/1.0）同口径；此前只取 rc==0 当绿，rc>=2 被误判过红。
    try:
        from experiments._m1_metrics import _looks_like_test_execution_error as _exec_err

        if _exec_err(res[0], res[1] + res[2]):
            return {"green": False, "rc": res[0], "unavailable": True}
    except Exception:
        logger.warning("AC2 门执行错误判据不可用，回退历史 rc==0 口径", exc_info=True)
    # BE（2026-10-21）：rc==0 但无有效通过（全 skip / xfail / deselect）→
    # 不可判定（unavailable），不是"gold fixed 仍红"（over_red）也不是绿。
    # 门①的语义是"buggy 红 + fixed 绿 = 缺陷特异"；fixed 侧没断言执行时
    # 两侧证据都不存在，必须保守放行到历史路由。
    if res[0] == 0 and not suite_has_effective_pass(res[1] + "\n" + res[2]):
        return {"green": False, "rc": res[0], "unavailable": True}
    return {"green": res[0] == 0, "rc": res[0], "unavailable": False}


#: 随裁决返回的摘要计数键（缺省一律 0，保证形状恒定）
_OFFICIAL_COUNT_KEYS: tuple[str, ...] = ("passed", "failed", "error", "skipped")


def _official_facts(
    reason: str,
    verdict: str = "unavailable",
    rc: int | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """gold 裁决的统一出参形状：结论 + 理由 + 退出码 + 摘要计数（缺省全 0）。

    计数一律随裁决返回，调用方（与事后审计）能看到"为什么是这个结论"，
    而不是只有一个布尔——`patch_evidence_level=gold` 的放行理由要能落地。
    """
    got = counts or {}
    payload: dict[str, Any] = {"verdict": verdict, "reason": reason, "rc": rc}
    for key in _OFFICIAL_COUNT_KEYS:
        payload[key] = int(got.get(key, 0))
    return payload


def _looks_like_execution_error(rc: int, output: str) -> bool:
    """执行错误判据：与 M1 事后裁决同一函数；委托不可用时回退 rc 结构性判据。

    回退口径与 `_run_test_against_code` 的历史兜底一致（保守：把 rc>=2 /
    负 rc 视为"根本没跑起来"），不因导入失败把执行错误读成断言失败。
    """
    try:
        from experiments._m1_metrics import _looks_like_test_execution_error as _exec_err

        return bool(_exec_err(rc, output))
    except Exception:
        logger.warning("B1 执行错误判据不可用（experiments._m1_metrics 委托失败），回退 rc 结构判据", exc_info=True)
        return rc >= 2 or rc < 0


def run_official_tests(
    test_code: str,
    patched_code: str,
    module_name: str | None,
    task_metadata: dict[str, Any] | None = None,
    timeout: int = _GATE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """B1（2026-11-05）：把官方测试跑在**打补丁的源码**上，返回三值 gold 裁决。

    执行原语与判绿口径与 M1 事后 repair 指标完全同源（同一个
    `_run_pytest_in_tmp` + 同一个执行错误判据 + 同一个"有效通过"谓词），
    使"图内证据门放行"与"事后记 repair=1.0"不会各说一套话。

    Returns:
        `{"verdict", "reason", "rc", "passed", "failed", "error", "skipped"}`：
        - **gold**：rc==0 且摘要有真实 passed——官方测试在补丁上全绿，
          这是"补丁经独立裁决"的最强证据；
        - **red**（reason="failed"）：rc==1，存在断言失败——补丁没让官方
          测试通过，是"改错了"的确定性证据；
        - **unavailable**：无官方测试材料 / 非法 module_name / 委托原语不可用 /
          收集期错误（rc>=2、负 rc、rc==5 零用例）/ rc==0 但零有效通过
          （全 skip / xfail）。**"没跑起来"一律不得读作"跑过了"**（F03/R16）。
    """
    if not (test_code or "").strip():
        return _official_facts("no_official_tests")
    if not module_name or not _SAFE_MODULE_RE.match(module_name):
        # 非法名不进委托层（名字即临时目录文件名与 import 目标）——与
        # `_run_test_against_code` 同口径，且在委托前拦下，零子进程成本
        return _official_facts("invalid_module")
    res = _pytest_in_tmp_raw(test_code, patched_code, module_name, timeout, task_metadata)
    if res is None:
        return _official_facts("runner_unavailable")
    rc, out, err = res
    counts = pytest_summary_counts(f"{out}\n{err}")
    summary = {
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "error": counts.get("error", 0),
        "skipped": counts.get("skipped", 0),
    }
    if _looks_like_execution_error(rc, f"{out}\n{err}"):
        return _official_facts("exec_error", rc=rc, counts=summary)
    if rc != 0:
        return _official_facts("failed", verdict="red", rc=rc, counts=summary)
    if not suite_has_effective_pass(f"{out}\n{err}"):
        return _official_facts("no_effective_pass", rc=rc, counts=summary)
    return _official_facts("gold", verdict="gold", rc=rc, counts=summary)


def specificity_verdict(
    test_code: str,
    gold_fixed_code: str | None,
    module_name: str | None,
    task_metadata: dict[str, Any] | None = None,
) -> str:
    """门①判定：当前红测试是否缺陷特异。

    Args:
        test_code: 当前生成测试全文。
        gold_fixed_code: gold 修复代码全文（state["gold_fixed_code"]，
            合成任务由 run_benchmark 从任务材料管道注入；None / 空串 =
            无 gold 材料——真实仓库场景，后续批次以变异体裁决替代）。
        module_name: 目标模块名。
        task_metadata: 与 M1 事后裁决同口径的任务材料（P0-1，
            2026-10-11 全面优化批次）：跨文件任务必传（委托层据此
            物化伴生模块树，避免 rc>=2 被误判过红）；未传时
            行为与历史逐位一致，零回归。

    Returns:
        - "specific_red"：gold fixed 上转绿（buggy 红 + fixed 绿，缺陷特异）；
        - "over_red"：gold fixed 上仍红（过红，F2P 三段不通过）；
        - "unavailable"：无 gold 材料 / 执行不可判定（保守放行，走历史
          路由进修复循环）。
    """
    if not gold_fixed_code or not gold_fixed_code.strip() or not (test_code and test_code.strip()):
        return "unavailable"
    res = _run_test_against_code(test_code, gold_fixed_code, module_name, task_metadata=task_metadata)
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
