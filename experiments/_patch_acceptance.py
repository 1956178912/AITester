"""补丁接收链的单一事实源（BW 轮，2026-10-23）。

背景：补丁从「写盘成功」到「gold 判正确」是一条**多门链**，每一门都在结果行
里留下判定值，但报告面只读其中一部分：

- `patch_precision`（R53，预注册 E3 要求的指标）自写入起报告面 **0 读者**；
- `patch_plausible_evidence` / `patch_plausible_invariant_violation`（P0-2）
  只写不读——前者是 `plausible` 的唯一可复核依据，后者是
  `correct=1 ∧ plausible=0` 的显式观测；
- `patch_abstain_signals`（批次 V，ADR-0020）只写不读——报告面看不到
  弃权由哪条不可信信号触发，也看不到弃权精确率；
- `patch_validated` / `patch_validate_verdict`（批次 XVI）只有测试读者，
  报告面看不到 filtered success 的覆盖率。

这些判定值都是**忠实**的，但它们的**分母与输入可达域**没有披露：

- `patch_precision=None` 只表示 `plausible=0`（无分母），既不是 0 也不是
  「无 gold 材料」；而 `plausible=1` 且 `repair_rate=None` 的 283 行会得到
  `precision=0.0`，把「没测」写成「测了且错」；
- `correct=1 ∧ plausible=0` 的 139 行让 `correct`/`plausible` 不是包含关系，
  `correct / plausible` 与 `correct / (plausible ∪ correct)` 是两个数；
- 弃权门在「失败且无补丁」的 608 行上没有可抑制对象，却与真正的抑制
  同记为 `abstained=True`；
- 验证层两个最强输入（`repo_verification` / `deterministic_repair_status`）
  在整个归档里**可达域为空**，594 行 `validated=True` 全部来自最弱的
  `patch_evidence_level ∈ {gold, sbfl}` 一档，其中实际只有 `sbfl`。

本模块只做**读侧分档与对账**：不改判定核、不改任何行的值与方向、不回填
历史行。词表与判定核同源（`patch_abstain_signal_names()` /
`patch_validate_verdict_names()`），由 `tests/test_patch_acceptance_bw.py`
逐项对照。

外部口径（本轮联网核对）：
- selective prediction：coverage = 接受数 / 可测数；selective risk = 接受中
  错误数 / 接受数（Geifman & El-Yaniv 的风险–覆盖曲线口径；覆盖率为 0 时
  不得把风险写成 0）。本模块的接受集是 `plausible=1`，错误集是
  `correct=0`（按 gold 可测分母另列）。
- abstention：Abstain and Validate（ICSE-SEIP 2026，arXiv:2510.03217）与
  LLM 弃权综述（arXiv:2407.18418）把「弃权精确率」定义为弃权决策中确实
  该弃权的占比。本模块按 ADR-0020 的转正判据，把它落成「被抑制的 passed
  中 false-fix 占比」，并把 gold 未测行单列。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# ═══ 补丁接收链的键名 ═══════════════════════════════════════════════════════

PLAUSIBLE_KEY = "patch_plausible"
CORRECT_KEY = "patch_correct"
PRECISION_KEY = "patch_precision"
EVIDENCE_KEY = "patch_plausible_evidence"
INVARIANT_KEY = "patch_plausible_invariant_violation"
REPAIR_RATE_KEY = "repair_rate"
PASSED_KEY = "passed"
PATCH_KEY = "patch"
ABSTAINED_KEY = "patch_abstained"
ABSTAIN_SIGNALS_KEY = "patch_abstain_signals"
VALIDATED_KEY = "patch_validated"
VALIDATE_VERDICT_KEY = "patch_validate_verdict"

# ═══ plausible 证据档（`_patch_plausible_evidence` 的返回域） ═══════════════

EVIDENCE_NO_STATE = "no_state"
EVIDENCE_NO_PATCH = "no_patch"
EVIDENCE_NO_HISTORY = "no_history"
EVIDENCE_REJECTED = "rejected"
EVIDENCE_APPLIED_THEN_REJECTED = "applied_then_rejected"
EVIDENCE_APPLIED = "applied"
EVIDENCE_BASES: tuple[str, ...] = (
    EVIDENCE_NO_STATE,
    EVIDENCE_NO_PATCH,
    EVIDENCE_NO_HISTORY,
    EVIDENCE_REJECTED,
    EVIDENCE_APPLIED_THEN_REJECTED,
    EVIDENCE_APPLIED,
)

#: `plausible=1` 的充分且必要证据档（「任一迭代写盘成功」口径）。
EVIDENCE_PLAUSIBLE_BASES = frozenset({EVIDENCE_APPLIED, EVIDENCE_APPLIED_THEN_REJECTED})

EVIDENCE_UNRECORDED = "evidence_unrecorded"
EVIDENCE_OTHER_PREFIX = "other:"

# ═══ gold 裁决状态（`correct=0` 的三种成因） ════════════════════════════════

CORRECT_MEASURED = "correct"
CORRECT_GOLD_INCORRECT = "gold_incorrect"
CORRECT_NO_GOLD = "no_gold"
CORRECT_UNRECORDED = "correct_unrecorded"
CORRECT_VOCAB: tuple[str, ...] = (
    CORRECT_MEASURED,
    CORRECT_GOLD_INCORRECT,
    CORRECT_NO_GOLD,
    CORRECT_UNRECORDED,
)

# ═══ 弃权门的可抑制对象（`patch_abstained=True` 的四种上下文） ═════════════

ABSTAIN_PASSED_WITH_PATCH = "passed_with_patch"
ABSTAIN_PASSED_NO_PATCH = "passed_no_patch"
ABSTAIN_FAILED_WITH_PATCH = "failed_with_patch"
ABSTAIN_FAILED_NO_PATCH = "failed_no_patch"
ABSTAIN_BUCKETS: tuple[str, ...] = (
    ABSTAIN_PASSED_WITH_PATCH,
    ABSTAIN_PASSED_NO_PATCH,
    ABSTAIN_FAILED_WITH_PATCH,
    ABSTAIN_FAILED_NO_PATCH,
)

# ═══ 验证层的输入域（`evaluate_patch_validation` 依次查看的三个证据源） ═════

VALIDATION_INPUTS: tuple[str, ...] = (
    "repo_verification",
    "deterministic_repair_status",
    "patch_evidence_level",
)

_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off"})


def flag(value: Any) -> int | None:
    """把归档里的 0/1 显式折叠成整数；认不出返回 None。

    归档里存在字符串形式的布尔值（BN 轮的教训：`bool("false")` 为真），
    所以这里不做 `bool(value)`，只认枚举集合。
    """
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_STRINGS:
            return 1
        if text in _FALSE_STRINGS:
            return 0
    return None


def plausible(row: Mapping[str, Any]) -> int | None:
    """`patch_plausible` 的折叠值；键缺席 → None（未记录，不是 0）。"""
    if PLAUSIBLE_KEY not in row:
        return None
    return flag(row.get(PLAUSIBLE_KEY))


def correct(row: Mapping[str, Any]) -> int | None:
    """`patch_correct` 的折叠值；键缺席 → None。"""
    if CORRECT_KEY not in row:
        return None
    return flag(row.get(CORRECT_KEY))


def correct_status(row: Mapping[str, Any]) -> str:
    """把 `correct=0` 拆成「gold 判错」/「无 gold 材料」/「未记录」。

    `_patch_correct` 在无 gold（`repair_rate=None`）时保守返回 0；报告面若把
    这个 0 读成「gold 判错」，就把「没测」写成了「测了且错」。
    """
    value = correct(row)
    if value is None:
        return CORRECT_UNRECORDED
    if value == 1:
        return CORRECT_MEASURED
    if REPAIR_RATE_KEY not in row or row.get(REPAIR_RATE_KEY) is None:
        return CORRECT_NO_GOLD
    return CORRECT_GOLD_INCORRECT


def precision_stored(row: Mapping[str, Any]) -> float | None:
    """行内 `patch_precision` 的数值；None / 非数值 → None。"""
    value = row.get(PRECISION_KEY)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def precision_expected(row: Mapping[str, Any]) -> float | None:
    """按行内 `correct / plausible` 复算的精确率（分母 0 → None）。"""
    denom = plausible(row)
    numer = correct(row)
    if denom in (None, 0) or numer is None:
        return None
    return numer / denom


def precision_mismatch(row: Mapping[str, Any]) -> bool:
    """行内精确率与 `correct/plausible` 是否不一致（双方都 None = 一致）。"""
    stored = precision_stored(row)
    expected = precision_expected(row)
    if stored is None or expected is None:
        return stored is not None or expected is not None
    return abs(stored - expected) > 1e-12


def evidence_basis(row: Mapping[str, Any]) -> str:
    """`patch_plausible_evidence["basis"]` 的分档；键缺席 → 未记录。"""
    if EVIDENCE_KEY not in row:
        return EVIDENCE_UNRECORDED
    evidence = row.get(EVIDENCE_KEY)
    if not isinstance(evidence, Mapping):
        return EVIDENCE_OTHER_PREFIX + "non_mapping"
    basis = evidence.get("basis")
    if basis in EVIDENCE_BASES:
        return str(basis)
    return EVIDENCE_OTHER_PREFIX + str(basis)


def evidence_plausible(basis: str) -> int | None:
    """证据档隐含的 plausible 值；认不出的档 → None（不参与对账）。"""
    if basis in EVIDENCE_PLAUSIBLE_BASES:
        return 1
    if basis in EVIDENCE_BASES:
        return 0
    return None


def evidence_mismatch(row: Mapping[str, Any]) -> bool:
    """证据档与 `patch_plausible` 是否矛盾（未记录/未知档不判矛盾）。"""
    value = plausible(row)
    expected = evidence_plausible(evidence_basis(row))
    if value is None or expected is None:
        return False
    return value != expected


def invariant_recomputed(row: Mapping[str, Any]) -> bool | None:
    """按行内两值复算 `correct=1 ∧ plausible=0`；任一缺席 → None。"""
    denom = plausible(row)
    numer = correct(row)
    if denom is None or numer is None:
        return None
    return numer == 1 and denom == 0


def invariant_flag(row: Mapping[str, Any]) -> int | None:
    """行内不变量标记；键缺席 → None（历史行，标记未落盘）。"""
    if INVARIANT_KEY not in row:
        return None
    return flag(row.get(INVARIANT_KEY))


def patch_present(row: Mapping[str, Any]) -> bool:
    """行内是否真有补丁文本（空白串按无补丁读）。"""
    return bool(str(row.get(PATCH_KEY) or "").strip())


def abstain_bucket(row: Mapping[str, Any]) -> str:
    """弃权门的可抑制对象：passed / patch 的四种组合。"""
    passed = flag(row.get(PASSED_KEY)) == 1
    has_patch = patch_present(row)
    if passed and has_patch:
        return ABSTAIN_PASSED_WITH_PATCH
    if passed:
        return ABSTAIN_PASSED_NO_PATCH
    if has_patch:
        return ABSTAIN_FAILED_WITH_PATCH
    return ABSTAIN_FAILED_NO_PATCH


def abstain_applicable(row: Mapping[str, Any]) -> bool:
    """弃权是否作用在某个可抑制对象上（失败且无补丁 → 无对象）。"""
    return abstain_bucket(row) != ABSTAIN_FAILED_NO_PATCH


def abstain_signals(row: Mapping[str, Any]) -> list[str]:
    """行内弃权信号列表；非列表 / 缺席 → 空列表（不猜）。"""
    raw = row.get(ABSTAIN_SIGNALS_KEY)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def abstain_signal_names() -> tuple[str, ...]:
    """弃权门信号键名——直接取判定核的公开清单，不在此另抄一份。"""
    from src.tools.patch_abstain import patch_abstain_signal_names

    return patch_abstain_signal_names()


def recompute_abstention(row: Mapping[str, Any]) -> dict[str, Any]:
    """把弃权判定核重跑在归档行上（只读对账，不回写）。"""
    from src.tools.patch_abstain import evaluate_patch_abstention

    return evaluate_patch_abstention(row)


def validation_inputs(row: Mapping[str, Any]) -> tuple[str, ...]:
    """验证门实际拿到输入的证据源；缺席/None 不算输入。"""
    available: list[str] = []
    for name in VALIDATION_INPUTS:
        value = row.get(name)
        if name == "patch_evidence_level":
            if value is not None:
                available.append(name)
        elif isinstance(value, Mapping):
            available.append(name)
    return tuple(available)


def validation_verdict(row: Mapping[str, Any]) -> str:
    """行内 `patch_validate_verdict`；键缺席 → 未记录。"""
    if VALIDATE_VERDICT_KEY not in row:
        return "unrecorded"
    return str(row.get(VALIDATE_VERDICT_KEY))


def validated(row: Mapping[str, Any]) -> int | None:
    """`patch_validated` 的折叠值；键缺席 → None。"""
    if VALIDATED_KEY not in row:
        return None
    return flag(row.get(VALIDATED_KEY))


def recompute_validation(row: Mapping[str, Any]) -> dict[str, Any]:
    """把验证判定核重跑在归档行上（只读对账，不回写）。"""
    from src.tools.patch_validate import evaluate_patch_validation

    return evaluate_patch_validation(row)


def filtered_success(row: Mapping[str, Any]) -> bool:
    """Abstain-and-Validate 的 filtered success 口径（复用判定核）。"""
    from src.tools.patch_validate import filtered_success as _filtered_success

    return _filtered_success(row)
