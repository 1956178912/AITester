"""测试套件修复管线（Suite Repair Pipeline, SRP）。

把路径 C 的三项实证发现整合为一条**零 LLM、可复算、fail-closed** 的管线，
用于把"零检出"的 LLM 测试套件修成"缺陷特异检出"。

## 为什么需要（2026-10-11 真实基准实测，全部可复算）

对 QuixBugs 50 任务 × 2 臂的实测中，`aitester` 有 **13 行 `detection_rate = 0.0`**
（有生成测试但零检出）。逐行归因 + 因果实验给出三个**量化结论**：

| 干预 | 翻转行数 |
|---|---|
| 仅注入路径 C 的机械触发见证 | **0 / 13** |
| **GCP 剪枝**（剔除在 gold 上失败的测试块） | **9 / 13（69%）** |
| **GCP + 见证安全门** | **12 / 13（92%）** |

即：**第一瓶颈不是"输入选得不好"，而是"LLM 测试里含有在正确实现上就失败的块"**。
这些块有两重危害：① 自身是假失败；② 压住 M1 的 F2P 第二段（要求 gold 绿），
使整行 `detection_rate` 归零。

## 三段管线（每段都 fail-closed，失败即降级而非产假信号）

1. **GCP 剪枝**（`gold_consistency_pruning`）：逐块在 gold 上执行，剔除失败的块；
   若**全部**块都失败 → 不产出空套件（会变成"恒红"假阳性），标记不可用。
2. **触发见证搜索**（`solver_directed_trigger`）：名称启发式 + hypothesis 搜索 +
   **行为差分验证**（行为归一化后比较，避免 generator 地址差异造成假见证）。
3. **见证安全门**（本模块）：**每一条**见证断言必须先在 gold 上通过才允许注入。
   实测：`minimum_spanning_tree` 的 24 条候选见证**全部**被安全门拒绝（0 通过）——
   若无此门，注入会引入新假失败，把 `detection` 从 1.0 打回 0.0（实测发生）。

## 与 M1 口径的关系

本管线**不改变** detection 的定义（buggy 红 ∧ gold 绿 ∧ 无收集错误）。
它只做减法（剔除不一致块）+ 加法（注入经 gold 验证的见证断言），
使既有定义的判定条件不再被无关噪声压住。

用法：
    from experiments.suite_repair_pipeline import repair_suite

    out = repair_suite(task=task, test_code=..., gold_code=..., fn_name="...")
    print(out.as_dict())
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SuiteRepairResult:
    """管线结果（全部字段可复算）。"""

    available: bool = False
    not_available_reason: str = ""
    repaired_code: str = ""
    blocks_total: int = 0
    blocks_kept: int = 0
    blocks_pruned: int = 0
    witnesses_found: int = 0
    witnesses_accepted: int = 0
    witnesses_rejected: int = 0
    stages_applied: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "not_available_reason": self.not_available_reason,
            "blocks_total": self.blocks_total,
            "blocks_kept": self.blocks_kept,
            "blocks_pruned": self.blocks_pruned,
            "witnesses_found": self.witnesses_found,
            "witnesses_accepted": self.witnesses_accepted,
            "witnesses_rejected": self.witnesses_rejected,
            "stages_applied": self.stages_applied,
        }


def _runs_green_on(code: str, test_code: str, module_name: str, timeout: int) -> bool | None:
    """在 code 上跑 test_code 是否全绿；不可判定返回 None。"""
    tmp = tempfile.mkdtemp(prefix="aitester_srp_")
    try:
        with open(os.path.join(tmp, f"{module_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        test_path = os.path.join(tmp, f"test_{module_name}.py")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        try:
            from src.utils.process_utils import run_with_timeout

            res = run_with_timeout(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                    test_path,
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": tmp},
                check=False,
                raise_on_timeout=True,
            )
        except subprocess.TimeoutExpired:
            return None
        return res.returncode == 0
    except Exception:
        logger.debug("SRP 执行失败", exc_info=True)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _witness_body(fn: str, module: str, w: Any, idx: int) -> str | None:
    """把一条见证转成独立测试函数体（ok → 等值断言；exc → pytest.raises）。"""
    args = ", ".join(repr(a) for a in w.args)
    if w.gold_behavior.startswith("ok:"):
        expected = w.gold_behavior.split(":", 1)[1]
        return f"from {module} import {fn}\n\ndef test_srp_witness_{idx}():\n    assert {fn}({args}) == {expected}\n"
    if w.gold_behavior.startswith("exc:"):
        exc = w.gold_behavior.split(":", 1)[1]
        return (
            f"from {module} import {fn}\nimport pytest\n\n"
            f"def test_srp_witness_{idx}():\n"
            f"    with pytest.raises({exc}):\n        {fn}({args})\n"
        )
    # timeout / 其他：不注入（无法写稳定断言）
    return None


def repair_suite(
    *,
    test_code: str,
    gold_code: str,
    buggy_code: str,
    fn_name: str,
    module_name: str | None = None,
    max_candidates: int = 60,
    timeout: int = 60,
) -> SuiteRepairResult:
    """执行三段管线（GCP → 见证搜索 → 安全门）。

    Args:
        test_code: LLM 生成的测试全文。
        gold_code: gold 修复后实现（判据基准）。
        buggy_code: 缺陷实现。
        fn_name: 目标函数名。
        module_name: 落盘模块名（默认与 `fn_name` 相同）。
        max_candidates: 见证搜索候选预算。
        timeout: 单次套件执行超时。

    Returns:
        `SuiteRepairResult`。`available=False` 表示管线未能产出可用套件
        （例如 GCP 判定全部块不一致且无安全见证），调用方应保留原套件。
    """
    from experiments.gold_consistency_pruning import prune_inconsistent_blocks
    from experiments.solver_directed_trigger import search_trigger_witnesses

    out = SuiteRepairResult()
    module = module_name or fn_name
    if not (test_code or "").strip() or not (gold_code or "").strip():
        out.not_available_reason = "empty_input"
        return out

    # ---- 阶段 1：GCP 剪枝 ----
    pr = prune_inconsistent_blocks(test_code=test_code, gold_code=gold_code, module_name=module, timeout=timeout)
    stats = pr.as_dict()
    out.blocks_total = int(stats["blocks_total"])
    out.blocks_kept = int(stats["blocks_kept"])
    out.blocks_pruned = int(stats["blocks_pruned"])
    base = pr.pruned_code if pr.available else test_code
    if pr.available and pr.not_available_reason != "already_green_on_gold":
        out.stages_applied.append("gcp")
    if not pr.available and pr.not_available_reason == "all_blocks_inconsistent":
        # GCP 全剔：仍可尝试用安全见证重建（见阶段 3），故不提前返回
        logger.info("SRP：GCP 判定全部块不一致，将由安全见证尝试重建")
        base = pr.head

    # ---- 阶段 2：触发见证搜索 ----
    wres = search_trigger_witnesses(
        buggy_code=buggy_code,
        gold_code=gold_code,
        fn_name=fn_name,
        module_name=module,
        max_candidates=max_candidates,
    )
    out.witnesses_found = len(wres.witnesses)

    # ---- 阶段 3：见证安全门（必须先在 gold 上通过） ----
    accepted: list[str] = []
    for i, w in enumerate(wres.witnesses):
        body = _witness_body(fn_name, module, w, i)
        if body is None:
            out.witnesses_rejected += 1
            continue
        # 安全门：在纯净 gold 上执行该断言
        if _runs_green_on(gold_code, body, module, timeout) is True:
            accepted.append(body)
            out.witnesses_accepted += 1
        else:
            out.witnesses_rejected += 1
            logger.info("SRP：见证 %d 未通过安全门（在 gold 上不通过），拒绝注入", i)
    if accepted:
        out.stages_applied.append("witness_injection")

    candidate = base.rstrip() + "\n\n" + "\n".join(accepted) if accepted else base

    # ---- 终检：修复后的套件必须在 gold 上全绿（否则不能作为检出候选） ----
    green = _runs_green_on(gold_code, candidate, module, timeout)
    if green is not True:
        out.not_available_reason = "repaired_suite_not_green_on_gold"
        out.repaired_code = candidate
        logger.info("SRP：修复后套件在 gold 上不全绿（%s），判不可用", green)
        return out
    if not candidate.strip():
        out.not_available_reason = "empty_after_repair"
        return out
    out.available = True
    out.repaired_code = candidate
    return out
