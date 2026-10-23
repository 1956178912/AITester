"""批次 VIII / XIV 观测层「判定核沉默」的单一事实源（BV 轮，2026-10-23）。

背景：两组判定键自写入起在报告面**零读者**（BU 轮普查的 11 键池里的两项）：

- `test_hacking_suspected` / `test_hacking_signals`（批次 VIII，ADR-0022）；
- `fl_constraint_verdict` / `fl_constraint_hit_rank` /
  `fl_constraint_changed_functions`（批次 XIV，ADR-0028）。

两者的沉默都是**多成因、同取值**：

- test-hacking 判定核在「无原码 / 无补丁 / 原码解析失败 / 补丁解析失败」时
  返回 `suspected=False, signals=[]`——与「三信号都跑过且没命中」完全同形。
  归档 5935 行里 20 行 `suspected=True`（真实命中）从未出现在任何报告面，
  而其余 5915 行的「不怀疑」分不清是判干净还是没看。
- FL 约束门在「无补丁 / 无定位 / 无原码 / 变更集合为空 / 无候选 / 异常」六种
  情形下都返回 `verdict="not_evaluable"`——六种成因共用一个标签，报告面连
  这一个标签都不读（归档 4442/5935 = 74.8% 落在这一档）。

本模块只做**读侧分档与推断**，不改判定核的判定值、不改任何行的值与方向：

- 新批次行自带 `test_hacking_status` / `fl_constraint_reason`（写侧增量），
  读侧按键值分档；
- 历史行（早于 BV）没有这两个键：hack 侧只能说「状态未记录」；FL 侧可按
  行内材料（`patch` / `llm_localization` / `fl_constraint_changed_functions`）
  **推断**成因。推断值与记录值必须**分列**，不得并档（推断看不到「无原码」
  与「异常」两支，只能给下界）。
"""

from __future__ import annotations

from typing import Any

# ═══ test-hacking 判定核（批次 VIII，ADR-0022） ═══════════════════════════════

HACK_SUSPECTED_KEY = "test_hacking_suspected"
HACK_SIGNALS_KEY = "test_hacking_signals"
HACK_STATUS_KEY = "test_hacking_status"

#: 判定核的求值状态词表——与 `src/tools/patch_test_hacking.hacking_evaluation_status_names()`
#: 逐项一致（`tests/test_verdict_silence_bv.py` 的对照锁盯这条）。`ok` 之外一律
#: 「没看」，判定值仍为 `False`。
HACK_STATUS_OK = "ok"
HACK_STATUS_EMPTY_ORIGINAL = "empty_original"
HACK_STATUS_EMPTY_PATCH = "empty_patch"
HACK_STATUS_PARSE_ERROR_ORIGINAL = "parse_error_original"
HACK_STATUS_PARSE_ERROR_PATCHED = "parse_error_patched"
HACK_STATUS_VOCAB: tuple[str, ...] = (
    HACK_STATUS_OK,
    HACK_STATUS_EMPTY_ORIGINAL,
    HACK_STATUS_EMPTY_PATCH,
    HACK_STATUS_PARSE_ERROR_ORIGINAL,
    HACK_STATUS_PARSE_ERROR_PATCHED,
)

#: 写侧兜底档：调用点自己的异常（`_target_code_after_patch` 抛错等），
#: 不是判定核的状态——单列，不并进上面五档。
HACK_STATUS_DETECTOR_ERROR = "detector_error"

#: 历史行（键缺席）的读法：状态**未记录**，不得读作 `ok`。
HACK_STATUS_UNRECORDED = "status_unrecorded"

#: 三个信号名——与 `src/tools/patch_test_hacking.hacking_signal_names()` 一致。
HACK_SIGNAL_NAMES: tuple[str, ...] = (
    "hardcoded_input_branch",
    "assert_weakened",
    "exception_swallow_added",
)

# ═══ FL Top-k 约束门（批次 XIV，ADR-0028） ═══════════════════════════════════

FL_VERDICT_KEY = "fl_constraint_verdict"
FL_HIT_RANK_KEY = "fl_constraint_hit_rank"
FL_CHANGED_KEY = "fl_constraint_changed_functions"
FL_REASON_KEY = "fl_constraint_reason"

#: 约束门的三种判定值（写侧 `_fl_constraint_result` 的返回域）。
FL_VERDICTS: tuple[str, ...] = ("hit", "miss", "not_evaluable")

#: 写侧成因词表：`ok` = 真的求值过（hit / miss 都属此档，成因都为 `ok`）；
#: 其余七档都是「没求值」，按 `_fl_constraint_result` 的早退顺序排列。
FL_REASON_OK = "ok"
FL_REASON_NO_STATE = "no_state"
FL_REASON_NO_PATCH = "no_patch"
FL_REASON_NO_LOCALIZATION = "no_localization"
FL_REASON_NO_ORIGINAL_CODE = "no_original_code"
FL_REASON_NO_CHANGED_FUNCTIONS = "no_changed_functions"
FL_REASON_NO_CANDIDATES = "no_candidates"
FL_REASON_ERROR = "error"
FL_REASON_VOCAB: tuple[str, ...] = (
    FL_REASON_OK,
    FL_REASON_NO_STATE,
    FL_REASON_NO_PATCH,
    FL_REASON_NO_LOCALIZATION,
    FL_REASON_NO_ORIGINAL_CODE,
    FL_REASON_NO_CHANGED_FUNCTIONS,
    FL_REASON_NO_CANDIDATES,
    FL_REASON_ERROR,
)

#: 读侧推断档（历史行没有 `fl_constraint_reason`，按行内材料反推）。
#: 推断只能看到三支：无补丁 / 无定位 / 变更集合为空——「无原码」「无候选」
#: 「异常」三支在行里没有痕迹，落 `inferred_unattributed`（**下界**，不是全部）。
FL_INFERRED_NO_PATCH = "inferred_no_patch"
FL_INFERRED_NO_LOCALIZATION = "inferred_no_localization"
FL_INFERRED_NO_CHANGED_FUNCTIONS = "inferred_no_changed_functions"
FL_INFERRED_UNATTRIBUTED = "inferred_unattributed"
FL_INFERRED_VOCAB: tuple[str, ...] = (
    FL_INFERRED_NO_PATCH,
    FL_INFERRED_NO_LOCALIZATION,
    FL_INFERRED_NO_CHANGED_FUNCTIONS,
    FL_INFERRED_UNATTRIBUTED,
)

#: 成因记录的三种来源，必须分列计数。
FL_BASIS_RECORDED = "recorded"
FL_BASIS_INFERRED = "inferred"
FL_BASIS_NOT_APPLICABLE = "not_applicable"
FL_BASIS_UNRECORDED_VERDICT = "unrecorded_verdict"


def _is_blank(value: Any) -> bool:
    """`None` / 空串 / 纯空白都算「没有材料」。"""
    return not str(value or "").strip()


def hack_status(row: dict[str, Any]) -> str:
    """该行 test-hacking 判定核的求值状态（读侧口径）。

    Returns:
        - 词表内取值（`ok` / `empty_*` / `parse_error_*` / `detector_error`）；
        - `status_unrecorded`：行里有判定键但没有状态键（批次早于 BV）；
        - `no_verdict`：行里连判定键都没有（批次早于批次 VIII）。

    词表外取值原样返回并加 `other:` 前缀——由调用方单列，不并进任何一档。
    """
    if HACK_SUSPECTED_KEY not in row:
        return "no_verdict"
    if HACK_STATUS_KEY not in row:
        return HACK_STATUS_UNRECORDED
    value = row.get(HACK_STATUS_KEY)
    if isinstance(value, str) and value in (*HACK_STATUS_VOCAB, HACK_STATUS_DETECTOR_ERROR):
        return value
    return f"other:{value}"


def hack_evaluated(row: dict[str, Any]) -> bool:
    """判定核**真的看过**这份补丁（`ok` 且三个信号都跑过）。"""
    return hack_status(row) == HACK_STATUS_OK


def hack_signals(row: dict[str, Any]) -> list[str]:
    """该行记录到的信号名（非列表 / 非字符串项一律丢弃，不猜）。"""
    raw = row.get(HACK_SIGNALS_KEY)
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, str)]


def fl_verdict(row: dict[str, Any]) -> str:
    """该行的约束门判定值：`hit` / `miss` / `not_evaluable` / `no_verdict` / `other:*`。

    `None` 是**失败分支的显式占位**（无终局状态 ⇒ 不可评估），按 `not_evaluable`
    读：它的成因由 `fl_constraint_reason`（BV 起写 `no_state`）或按材料推断给出。
    不这么读的话，失败分支行会落进 `other:None`，而它们的成因键（`no_state`）反而
    被忽略——「没状态」就成了一个既不是不可评估、也不是未记录的第四类暗档。
    """
    if FL_VERDICT_KEY not in row:
        return "no_verdict"
    value = row.get(FL_VERDICT_KEY)
    if value is None:
        return "not_evaluable"
    if isinstance(value, str) and value in FL_VERDICTS:
        return value
    return f"other:{value}"


def fl_changed_functions(row: dict[str, Any]) -> list[str]:
    """该行的变更函数集合（非列表 / 非字符串项一律丢弃）。"""
    raw = row.get(FL_CHANGED_KEY)
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, str)]


def infer_fl_reason(row: dict[str, Any]) -> str:
    """按行内材料推断 `not_evaluable` 的成因（历史行用；**下界**，非全集）。

    推断顺序与 `run_benchmark._fl_constraint_result` 的早退顺序一致：
    `no_patch` → `no_localization` → `no_changed_functions`。三支都不成立时
    落 `inferred_unattributed`——「无原码 / 无候选 / 异常」三支在行里没有
    可比对的痕迹，**不得**折进上面任何一档。
    """
    if _is_blank(row.get("patch")):
        return FL_INFERRED_NO_PATCH
    if not row.get("llm_localization"):
        return FL_INFERRED_NO_LOCALIZATION
    if not fl_changed_functions(row):
        return FL_INFERRED_NO_CHANGED_FUNCTIONS
    return FL_INFERRED_UNATTRIBUTED


def fl_reason(row: dict[str, Any]) -> tuple[str, str]:
    """该行约束门成因与来源：`(成因, 来源)`。

    来源四档（必须分列，不得并档）：

    - `recorded`：行内有 `fl_constraint_reason`（BV 之后的新批次）；
    - `inferred`：判定为 `not_evaluable` 但成因键缺席，按行内材料推断（下界）；
    - `not_applicable`：判定为 `hit` / `miss`——成因就是「求值过」，无需成因键；
    - `unrecorded_verdict`：连判定键都没有（批次早于批次 XIV）。
    """
    verdict = fl_verdict(row)
    if verdict == "no_verdict":
        return ("no_verdict", FL_BASIS_UNRECORDED_VERDICT)
    if verdict in {"hit", "miss"}:
        return (FL_REASON_OK, FL_BASIS_NOT_APPLICABLE)
    if verdict != "not_evaluable":
        # 词表外判定值：既不能当求值过，也不能当六种成因之一。
        return (f"other:{verdict}", FL_BASIS_RECORDED)
    if FL_REASON_KEY in row:
        reason = row.get(FL_REASON_KEY)
        if isinstance(reason, str) and reason in FL_REASON_VOCAB:
            return (reason, FL_BASIS_RECORDED)
        return (f"other:{reason}", FL_BASIS_RECORDED)
    return (infer_fl_reason(row), FL_BASIS_INFERRED)


def fl_evaluated(row: dict[str, Any]) -> bool:
    """约束门**真的求值过**（判定为 `hit` / `miss`，且成因键不自相矛盾）。"""
    if fl_verdict(row) not in {"hit", "miss"}:
        return False
    return not fl_reason_mismatch(row)


def fl_reason_mismatch(row: dict[str, Any]) -> bool:
    """成因键与判定值自相矛盾（写侧缺陷信号，读侧只点名不修正）。"""
    verdict = fl_verdict(row)
    if FL_REASON_KEY not in row:
        return False
    reason = row.get(FL_REASON_KEY)
    if not isinstance(reason, str):
        return True
    if verdict in {"hit", "miss"}:
        return reason != FL_REASON_OK
    if verdict == "not_evaluable":
        return reason == FL_REASON_OK
    return False
