"""编辑意图确定性落盘引擎（修复引擎第二阶段核心，2026-10-07 批次 III）。

背景（前沿实证，引用核验 2026-10-07）：
    - arXiv:2609.00227（GitOps 修复实测）：严格 unified diff 无人值守场景
      几乎全失败，宽容工具约 1/7 被静默错误应用——结论是「LLM 只输出
      字段级意图、编辑由确定性管道执行」；
    - Diff-XYZ（arXiv:2510.12487）：search/replace 格式在大模型上的
      表现优于自由 udiff 变体；
    - Minimal-Diff 口径（PatchPilot ICML'25 同思路）：最小补丁优于
      整文件重写（E7 工作表实证整文件替换带 LLM 格式伪影/无关注释）。

本模块把补丁产出从「LLM 整文件重写」升级为「LLM 输出结构化编辑
意图 + 确定性引擎落盘」：

    意图格式（debugger JSON 响应的附加字段）：
        "edit_intents": [{"old_str": "<原文唯一锚点>", "new_str": "<替换>"}, ...]

    确定性应用（apply_edit_intents）：
        1. 逐条校验：old_str 非空、old_str != new_str、在当前工作副本中
           **恰好出现一次**（锚点不唯一 → 整体拒绝，杜绝静默错应用）；
        2. 顺序应用（前一条的结果是后一条的工作副本，多 Hunk 场景
           每处一条意图）；
        3. 原子性：任一条拒绝 → 丢弃全部修改，返回原码（调用方回落
           legacy 整文件补丁通道）；
        4. AST 语法门：应用结果须可被 ast.parse（原文本就不可解析时
           跳过该门——不能因存量语法错误误杀合法编辑）。

开关：EDIT_INTENT_ENABLE（默认 false，ADR-0003 惯例——A/B 实验对照
用；开启后 debugger prompt 追加意图输出契约，debug() 内确定性应用，
成功则用编辑结果替换整文件 patch）。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "EDIT_INTENT_ENABLE"


def edit_intent_enabled() -> bool:
    """编辑意图通道开关（默认关；A/B 对照与灰度用）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


EDIT_INTENT_PROMPT_SECTION = (
    "【结构化编辑意图（必须输出）】除常规字段外，在 JSON 中追加 edit_intents 字段："
    '[{"old_str": "...", "new_str": "..."}]。old_str 必须是从被测代码逐字符复制的'
    "连续代码行（含缩进与空行），且在全文中**恰好出现一次**；new_str 为替换后的"
    "代码（删除代码时为空字符串）。多处修改按从上到下顺序各输出一条（多 Hunk "
    "场景每处一条）。该字段将由确定性引擎最小化应用，请保证锚点精确、不要"
    "重写无关代码。"
)


def parse_edit_intents(value: Any) -> list[dict[str, str]]:
    """校验并归一 LLM 输出的编辑意图（非法条目剔除，非法整体 → 空列表）。

    合法条目：dict 且 old_str/new_str 均为 str，old_str 非空且 != new_str。
    """
    if not isinstance(value, list) or not value:
        return []
    intents: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        old_str = item.get("old_str")
        new_str = item.get("new_str")
        if not isinstance(old_str, str) or not isinstance(new_str, str):
            continue
        if not old_str or old_str == new_str:
            continue
        intents.append({"old_str": old_str, "new_str": new_str})
    return intents


def apply_edit_intents(code: str, intents: list[dict[str, str]]) -> dict[str, Any]:
    """确定性应用编辑意图（锚点唯一性 + 原子性 + AST 语法门）。

    Returns:
        {"ok": bool, "code": str, "applied": int, "total": int,
         "diagnostics": [str, ...]}——ok=False 时 code 为原码（原子回退）。
    """
    total = len(intents)
    diagnostics: list[str] = []
    if not code.strip():
        return {"ok": False, "code": code, "applied": 0, "total": total, "diagnostics": ["empty_original_code"]}
    working = code
    applied = 0
    for idx, intent in enumerate(intents, start=1):
        old_str = intent.get("old_str", "")
        occurrences = working.count(old_str)
        if occurrences != 1:
            diagnostics.append(f"intent_{idx}_anchor_not_unique:{occurrences}")
            logger.warning("编辑意图 %d/%d 锚点出现 %d 次（须恰为 1），整体拒绝", idx, total, occurrences)
            return {"ok": False, "code": code, "applied": 0, "total": total, "diagnostics": diagnostics}
        working = working.replace(old_str, intent.get("new_str", ""), 1)
        applied += 1
    # AST 语法门：结果必须可解析（原文本本就不可解析时跳过——存量语法
    # 错误不应误杀合法编辑；该场景由下游执行层自然暴露）
    try:
        ast.parse(working)
    except SyntaxError as exc:
        try:
            ast.parse(code)
        except SyntaxError:
            diagnostics.append(f"result_syntax_error_preexisting:{exc.msg}")
            return {"ok": True, "code": working, "applied": applied, "total": total, "diagnostics": diagnostics}
        diagnostics.append(f"result_syntax_error:{exc.msg}")
        logger.warning("编辑意图应用结果语法错误（%s），原子回退", exc.msg)
        return {"ok": False, "code": code, "applied": 0, "total": total, "diagnostics": diagnostics}
    diagnostics.append(f"applied:{applied}/{total}")
    return {"ok": True, "code": working, "applied": applied, "total": total, "diagnostics": diagnostics}
