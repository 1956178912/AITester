"""Gold 一致性剪枝（Gold-Consistency Pruning, GCP）。

**动机（2026-10-11 真实基准实测发现，本模块解决的是被实测证明的最大单点损失）**

对 QuixBugs 50 任务 × 2 臂的实测中，`aitester` 有 **13 行 `detection_rate = 0.0`
（有生成测试但零检出）**。逐行归因显示两类原因：

1. **LLM 写了错误的期望值**：例如 `is_valid_parenthesization` 的生成测试含
   `("(((", True)`、`("(()", True)`——缺陷版恰好返回 `True` 所以"通过"，
   而**正确版返回 `False`** → 这些断言在 gold 上失败 → M1 的 F2P 第二段
   （buggy 红 **∧** gold 绿）被拒 → 整行 `detection_rate = 0.0`。
2. **测试自身在正确实现上不通过**（导入错误、期望值错误、超时）。

**关键实测数字（零 LLM，`experiments/results/pilot_mdo_full50/`）**

| 干预 | 翻转行数 |
|---|---|
| 仅注入路径 C 的机械触发见证 | **0 / 13** |
| **按 gold 剔除不一致测试块** + 注入见证 | **7 / 13（54%）** |

> 即：**真正的第一瓶颈不是"输入选得不好"，而是"LLM 测试中包含在正确实现上就失败的块"**——
> 这些块一方面直接造成假失败，另一方面**压住了检出判定**（F2P 第二段要求 gold 绿）。

**做法（保守、可复算）**

1. 按顶层 `def test_*` / `class Test*` 切块，保留文件头（import 与 module 级 setup）；
2. **逐块**在 gold 修复版上执行；仅保留**通过**的块；
3. 全部块都被剔除时**返回空**（`available=False`）而不是产出"净化后必绿"的假套件——
   否则会把 `detection` 抬成"恒红"（假阳性）。
4. 剔除是**减法**：不新增断言、不修改被测代码，因此不引入新的假阳性来源。

**与 M1 口径的关系**：本模块只是把"不该在 gold 上失败的块"去掉，
使 F2P 第二段（gold 绿）不再被无关噪声压住；它**不改变** detection 的定义。

用法：
    from experiments.gold_consistency_pruning import prune_inconsistent_blocks

    res = prune_inconsistent_blocks(test_code=..., gold_code=..., module_name="t")
    print(res.as_dict())    # kept / pruned / available
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_BLOCK_SPLIT = re.compile(r"(?m)^(?=def test_|class Test)")


@dataclass
class PruneResult:
    """剪枝结果（全部可复算）。"""

    available: bool = False
    not_available_reason: str = ""
    head: str = ""
    kept_blocks: list[str] = field(default_factory=list)
    pruned_blocks: list[str] = field(default_factory=list)
    pruned_reasons: list[str] = field(default_factory=list)

    @property
    def pruned_code(self) -> str:
        return self.head + "\n".join(self.kept_blocks)

    @property
    def n_pruned(self) -> int:
        return len(self.pruned_blocks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "not_available_reason": self.not_available_reason,
            "blocks_total": len(self.kept_blocks) + len(self.pruned_blocks),
            "blocks_kept": len(self.kept_blocks),
            "blocks_pruned": len(self.pruned_blocks),
            "pruned_reasons": self.pruned_reasons[:10],
        }


def _run_suite(code: str, test_code: str, module_name: str, timeout: int) -> int | None:
    """在 code 上跑测试，返回 pytest 退出码（不可判定返回 None）。"""
    tmp = tempfile.mkdtemp(prefix="aitester_gcp_")
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
        return res.returncode
    except Exception:
        logger.debug("GCP 执行失败", exc_info=True)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prune_inconsistent_blocks(
    *,
    test_code: str,
    gold_code: str,
    module_name: str,
    timeout: int = 60,
    max_blocks: int = 60,
) -> PruneResult:
    """剔除"在 gold 修复版上失败"的测试块。

    Args:
        test_code: LLM 生成的测试全文。
        gold_code: gold 修复后的实现源码（判据基准）。
        module_name: 模块名（与测试 import 同名）。
        timeout: 单次套件执行超时。
        max_blocks: 块数上限（防退化输入）。

    Returns:
        `PruneResult`。`available=False` 的三种情形：
        ① 输入为空；② 无块可切；③ **全部块都被剔除**（此时不应产出空套件）。
    """
    out = PruneResult()
    if not (test_code or "").strip() or not (gold_code or "").strip():
        out.not_available_reason = "empty_input"
        return out
    if _run_suite(gold_code, test_code, module_name, timeout) == 0:
        # 原套件在 gold 上本就全绿 → 无可剪枝
        out.available = True
        out.head = test_code
        out.kept_blocks = []
        out.not_available_reason = "already_green_on_gold"
        return out

    parts = _BLOCK_SPLIT.split(test_code)
    if len(parts) < 2:
        out.not_available_reason = "no_splittable_blocks"
        return out
    head = parts[0]
    blocks = [b for b in parts[1:] if b.strip()][:max_blocks]
    kept: list[str] = []
    pruned: list[str] = []
    reasons: list[str] = []
    for b in blocks:
        rc = _run_suite(gold_code, head + "\n" + b, module_name, timeout)
        if rc == 0:
            kept.append(b)
        else:
            pruned.append(b)
            name = b.splitlines()[0][:60] if b.splitlines() else "?"
            reasons.append(f"{name} → rc={rc}")
    if not kept:
        # 全部被剔除：产出空套件会让 detection 变成"恒红-不绿"或不可测，
        # 保守返回不可用，由调用方决定（不产出净化后的假套件）。
        out.not_available_reason = "all_blocks_inconsistent"
        out.head = head
        out.pruned_blocks = pruned
        out.pruned_reasons = reasons
        return out
    out.available = True
    out.head = head
    out.kept_blocks = kept
    out.pruned_blocks = pruned
    out.pruned_reasons = reasons
    return out
