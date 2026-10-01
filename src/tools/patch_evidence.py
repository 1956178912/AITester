"""
P0（2026-09-30 独立审查 N9/R33，P0）：源码补丁证据门（确定性）。

背景：
    默认链路下，executor 失败一律进入"改源码"分支，唯一的"这是测试的错"
    信号是对 LLM 自由文本诊断做关键词匹配（非确定性、不可复现）。当生成
    测试的断言本身写错（领域内最主要的失败模式，ChatTester / TestGenEval
    / TestART 三方独立收敛）时，系统会去修改**正确的生产代码**，直到那个
    错误断言通过——成功率上升而源码被破坏（N9）。

    前沿共识（§4.2）：补丁须有**确定性证据**（规约 / gold / 谱系定位 /
    差分），而非 LLM 自由文本。本模块提供零 LLM 成本的"补丁证据等级"
    判定，供 _patch_applier_node 在写盘前做证据门：

    证据等级（从高到低）：
    - "gold"：state["repo_verification"] 表明 gold 测试裁决通过（最强）；
    - "sbfl"：FL_SPECTRAL_ENABLE=true 且 fl_spectral_focus 非空，且补丁
      改动的行与 Top-k 可疑行有重叠（谱系定位证据）；
    - "keyword"：LLM 诊断文本命中 _TEST_GEN_DIAGNOSIS_KEYWORDS（历史
      口径，非确定性）；
    - "none"：无任何确定性证据。

    证据门（PATCH_EVIDENCE_GATE_ENABLE，默认 true）：
    - 等级 "gold" / "sbfl" → 放行（有独立裁决 / 定位证据）；
    - 等级 "keyword" / "none" → 拒绝写盘（patch_applied=False，
      源码保持原样），把该轮标记为 source_patched_unverified=True。

    历史口径（PATCH_EVIDENCE_GATE_ENABLE=false，opt-out）：
    行为与历史完全一致（证据判定仍计算并写入 state，但不阻断写盘），
    供消融实验"证据门 on/off"对照。

设计原则（保守、零 LLM 成本、默认开启但可 opt-out）：
    - 纯数据 + AST 判定，无 LLM 调用；
    - 任何异常 → 保守降级 "none"（不误放行）；
    - 判定结果写入 state["patch_evidence_level"] + state
      ["source_patched_unverified_count"]（纯观测，供实验分析消费；
      默认开启证据门时该计数 = 被门拒绝的次数，opt-out 时 = 0 占位）。
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "PATCH_EVIDENCE_GATE_ENABLE"


def patch_evidence_gate_enabled() -> bool:
    """证据门开关（PATCH_EVIDENCE_GATE_ENABLE，默认 true——N9 防线）。

    设 false 时保留历史口径（证据判定仍计算写入 state，但不阻断写盘），
    供"证据门 on/off"消融实验。
    """
    return os.getenv(_ENV, "true").lower() in ("true", "1", "on")


# 历史"测试生成错误"关键词（与 workflow._TEST_GEN_DIAGNOSIS_KEYWORDS
# 同口径——仅作为最低等级证据，不再是唯一路由依据）。
_KEYWORDS: tuple[str, ...] = (
    "测试生成错误",
    "测试设计存在错误",
    "test code",
    "测试用例",
    "期望的异常类型",
)


def _keywords_hit(diagnosis: str) -> bool:
    if not diagnosis:
        return False
    return any(kw in diagnosis for kw in _KEYWORDS)


def _patch_changed_lines(original_code: str, new_code: str) -> set[int]:
    """unified diff 下，new_code 中被新增/修改的行号集合（AST 保守口径）。

    以 difflib.unified_diff 提取"以 + 开头且非 +++ 的行"，映射到
    new_code 的行号。用于与 fl_spectral_focus 的 Top-k 行求重叠
    （sbfl 证据判定）。任何异常 → 空集（保守）。
    """
    if not new_code or new_code == original_code:
        return set()
    diff_lines = difflib.unified_diff(
        original_code.splitlines(keepends=False),
        new_code.splitlines(keepends=False),
        fromfile="a",
        tofile="b",
    )
    changed: set[int] = set()
    new_line = 0
    for line in diff_lines:
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            # 解析 @@ -a,b +c,d @@ 的 new 侧起始行
            try:
                plus_part = line.split("+", 2)[1]
                start_s = plus_part.split(",")[0].strip()
                new_line = int(start_s)
            except (IndexError, ValueError):
                new_line = 0
            continue
        if line.startswith("+") and not line.startswith("+++"):
            new_line += 1
            changed.add(new_line)
        elif not line.startswith("-"):
            new_line += 1
    return changed


def _ast_line_numbers(code: str) -> set[int]:
    """AST 可执行行号集合（保守：SyntaxError 时退化为全行）。"""
    if not code:
        return set()
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return set(range(1, len(code.splitlines()) + 1))
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.stmt, ast.expr)) and hasattr(node, "lineno"):
            lines.add(int(node.lineno))
    return lines


def assess_patch_evidence(
    state: dict[str, Any],
    original_code: str,
    new_code: str,
) -> str:
    """判定本轮源码补丁的确定性证据等级（纯数据，零 LLM 成本）。

    返回 "gold" / "sbfl" / "keyword" / "none"（取最高命中等级）。

    判定优先级：
    1. gold：state["repo_verification"] 非空且其中 passed=True（gold
       测试独立裁决通过——最强证据）；
    2. sbfl：fl_spectral_focus（O2 谱系定位）非空，且补丁改动行与
       Top-k 可疑行有重叠；
    3. keyword：LLM 诊断文本命中历史关键词（非确定性，仅兜底）；
    4. none：以上均未命中。

    任何读取异常 → 保守 "none"（不误放行）。
    """
    # 1. gold 证据
    try:
        repo_ver = state.get("repo_verification")
        if isinstance(repo_ver, dict) and repo_ver.get("passed") is True:
            return "gold"
    except Exception:
        pass

    # 2. sbfl 证据（谱系定位与补丁改动行重叠）
    try:
        fl_focus = state.get("fl_spectral_focus")
        if isinstance(fl_focus, dict):
            top_k = fl_focus.get("top_k") or []
            top_lines = {int(item.get("line", 0)) for item in top_k if item.get("line")}
            if top_lines:
                changed = _patch_changed_lines(original_code, new_code)
                if changed & top_lines:
                    return "sbfl"
    except Exception:
        pass

    # 3. keyword 证据（历史口径，非确定性兜底）
    try:
        diagnosis = str(state.get("diagnosis") or "")
        if _keywords_hit(diagnosis):
            return "keyword"
    except Exception:
        pass

    return "none"


def evidence_allows_write(level: str) -> bool:
    """证据门判定：该等级是否放行源码写盘。

    - "gold" / "sbfl" → True（有独立裁决 / 定位证据）；
    - "keyword" / "none" → False（仅 LLM 自由文本或无证据 → 拒绝，
      源码保持原样，该轮标记 source_patched_unverified）。

    设计意图：把"这是测试的错"的路由依据从关键词（非确定性）升级为
    确定性证据；关键词只保留为"可观测"（仍可被 M5 的
    test_regenerated_pass_unverified 标记），不再是写盘放行条件。
    """
    return level in ("gold", "sbfl")
