"""BI（2026-10-22）：写盘前静态预检的「读不懂 ⇒ 通过」source 侧收口锁。

缺陷族（F03 静态侧，与 BD–BH 的 `rc==0` / `passed=True` 判绿同族，落在
`patch_applier` 的两道写盘前守卫上）。改前实测（Python 3.14.6，零 LLM）：

1. **命名契约四义 `contract_ok=True`**：`(True, [])` 同时表示"比较过且无符号
   被删"、"原始代码读不懂（基准符号集为空 ⇒ 从未比较）"、"补丁读不懂但原文
   零模块符号"、"`PATCH_CONTRACT_CHECK=false` 恒放行"。生产消费点
   `_check_patch_safety` 无条件调用它，故原文为 py2 `print` 语句时，删除模块级
   符号的补丁**通过守卫并写盘**，`contract_missing_symbols` 保持 `null`，
   日志零披露（本文件 §6 用真实 `_patch_applier_node` 复现该形状）。
2. **补丁侧读不懂被误归因**：原文可解析且含模块符号、补丁无法解析时，旧实现
   把 `missing = 原符号 − ∅` 报成"补丁删除了 N 个模块级符号"，并经
   `contract_missing_symbols` / 1.3 降级链把这句**假陈述**送进读数。
3. **危险 API 差集静默 fail-open**：`dangerous_api_added` 与命名契约共用
   "解析失败 ⇒ 空集"的假设（旧 docstring 称"由 safe_apply_patch 的 ast.parse
   兜底"，该前提只在本地链路成立，G 轮已就同一前提在 repo 片段链路修过同型
   缺陷）。补丁读不懂 ⇒ 差集恒空 ⇒ "无新增危险 API"。
4. **消费侧无状态维度**：两道守卫都没有 status，读它们的结果只能靠"空/非空"。

修复口径（**判定值逐字节不变**，只补披露）：两守卫新增可选 `outcome_sink`，
逐条追加 `{check, status, reason}`；`_check_patch_safety` 汇聚为 worst-of
（两道守卫相互独立 ⇒ 最差者优先，与 BG 的"任一后端 ok ⇒ ok"方向相反）写入
`state` 通道键 `safety_check_status` / `safety_check_outcomes`；`type_repair`
的契约回环补 `contract_status` / `contract_reason` / `contract_outcomes`
（历史 `contract_ok` / `missing_symbols` 口径不动）。词表与聚合函数收敛到
`src/utils/check_status.py` 单一事实源，本文件 §1 锁三处取值逐字相同。
"""

from __future__ import annotations

import ast
import logging
from typing import Any
from unittest.mock import patch

import pytest

import src.tools.patch_applier as pa_mod
from src.graph import nodes as nodes_mod
from src.graph.state import AITesterState, create_initial_state
from src.tools import testless_validation as tv
from src.tools import type_repair as tr
from src.utils import check_status as cs

# ─── 语料 ────────────────────────────────────────────────────────────────
_CLEAN = "def f() -> int:\n    return 1\n"
_WITH_CONST = "def f() -> int:\n    return 1\n\n\nCONST = 3\n"
_PATCH_DROP_CONST = "def f() -> int:\n    return 2\n"  # 删掉了 CONST
_WITH_CONST_2 = "def f() -> int:\n    return 2\n\n\nCONST = 3\n"  # 改了函数体、保留 CONST
_PATCH_DANGEROUS = "import os\n\n\ndef f() -> int:\n    return os.system('ls')\n"
# 原代码已自带危险调用（差集口径下不算"新增"）
_ORIG_HAS_OS = "import os\n\n\ndef f() -> int:\n    return os.system('ls')\n\n\nCONST = 3\n"
_BROKEN = "def f(:\n"  # 原文侧读不懂
_PY2_PRINT = 'print "x"\n\n\ndef f():\n    return 1\n'
_BROKEN_PATCHED = "def f(:\n    return CONST\n\n\nCONST = 3\n"
_NO_SYMBOLS = "import os\n"  # 可解析但无模块级符号
_BLIND_VALUE = "x = '\ud800'\n"  # ast.parse 抛 UnicodeEncodeError（ValueError 子类）


def _old_dangerous_api_added(original_code: str, patched_code: str) -> list[str]:
    """改前 `dangerous_api_added` 的判定公式（HEAD 逐字复刻，用于不变性锁）。"""
    if not original_code or not patched_code:
        return []
    before = pa_mod._collect_dangerous_calls(original_code)
    after = pa_mod._collect_dangerous_calls(patched_code)
    return sorted(after - before)


def _old_check_naming_contract(original_code: str, patched_code: str) -> tuple[bool, list[str]]:
    """改前 `check_naming_contract` 的判定公式（开关默认开时成立）。"""
    if not original_code or not patched_code:
        return True, []
    original_symbols = pa_mod._collect_module_level_symbols(original_code)
    patched_symbols = pa_mod._collect_module_level_symbols(patched_code)
    if not original_symbols:
        return True, []
    missing = sorted(original_symbols - patched_symbols)
    if missing:
        return False, missing
    return True, []


def _sink_status(sink: list[dict[str, Any]], check: str) -> tuple[str, str]:
    """取某个 check 的最后一条 (status, reason)。"""
    hits = [o for o in sink if o.get("check") == check]
    assert hits, f"sink 未记录 {check}：{sink}"
    return str(hits[-1]["status"]), str(hits[-1]["reason"])


# ═══ 1. 单一事实源：三处词表逐字相同、两种聚合方向不同 ══════════════════════


class TestVocabularySingleSource:
    def test_four_values_identical_across_three_layers(self) -> None:
        """BI 的 check_status == BG 的 STATIC_CHECK_* == BH 的 VALIDATION_*。"""
        assert (
            (cs.CHECK_OK, cs.CHECK_DISABLED, cs.CHECK_UNAVAILABLE, cs.CHECK_ERROR)
            == (
                tr.STATIC_CHECK_OK,
                tr.STATIC_CHECK_DISABLED,
                tr.STATIC_CHECK_UNAVAILABLE,
                tr.STATIC_CHECK_ERROR,
            )
            == (tv.VALIDATION_OK, tv.VALIDATION_DISABLED, tv.VALIDATION_UNAVAILABLE, tv.VALIDATION_ERROR)
        )
        assert (cs.CHECK_OK, cs.CHECK_DISABLED, cs.CHECK_UNAVAILABLE, cs.CHECK_ERROR) == (
            "ok",
            "disabled",
            "unavailable",
            "error",
        )

    def test_precedence_tuples_identical(self) -> None:
        """三处"最差者优先"次序逐字相同（error > unavailable > disabled > ok）。"""
        assert cs.CHECK_STATUS_PRECEDENCE == tv._STATUS_PRECEDENCE
        assert cs.CHECK_STATUS_PRECEDENCE == (
            cs.CHECK_ERROR,
            cs.CHECK_UNAVAILABLE,
            cs.CHECK_DISABLED,
            cs.CHECK_OK,
        )

    def test_vocabulary_covers_all_layer_literals(self) -> None:
        assert {
            tr.STATIC_CHECK_OK,
            tr.STATIC_CHECK_DISABLED,
            tr.STATIC_CHECK_UNAVAILABLE,
            tr.STATIC_CHECK_ERROR,
            tv.VALIDATION_OK,
            tv.VALIDATION_DISABLED,
            tv.VALIDATION_UNAVAILABLE,
            tv.VALIDATION_ERROR,
        } == cs.CHECK_STATUS_VOCABULARY

    def test_aggregation_directions_differ_by_design(self) -> None:
        """可替换后端取 any-ok；独立检查取 worst——同一输入两方向结论相反。"""
        mixed = [cs.CHECK_OK, cs.CHECK_ERROR]
        assert cs.any_measurable_status(mixed) == cs.CHECK_OK
        assert cs.worst_check_status(mixed) == cs.CHECK_ERROR

    def test_any_measurable_reproduces_type_repair_aggregation(self) -> None:
        """共享聚合器与 BG 历史实现逐组合等价（含空集与未知取值）。"""
        combos = [
            [],
            ["ok"],
            ["disabled"],
            ["unavailable"],
            ["error"],
            ["error", "unavailable"],
            ["unavailable", "disabled"],
            ["error", "disabled"],
            ["ok", "error"],
            ["nonsense"],
            ["nonsense", "disabled"],
            [None],  # type: ignore[list-item]
        ]
        for statuses in combos:
            expected = tr._overall_static_check_status([{"backend": "b", "status": s} for s in statuses])
            assert cs.any_measurable_status(statuses) == expected, statuses

    def test_worst_reproduces_testless_layer_aggregation(self) -> None:
        """共享聚合器与 BH 历史实现逐组合等价（含缺 status 键与未知取值）。"""
        combos = [
            [],
            ["ok"],
            ["disabled"],
            ["unavailable"],
            ["error"],
            ["ok", "error"],
            ["ok", "disabled", "unavailable"],
            ["nonsense"],
            [None],  # type: ignore[list-item]
        ]
        for statuses in combos:
            layers = {f"L{i}": ({"status": s} if s is not None else {}) for i, s in enumerate(statuses)}
            expected = tv._worst_layer_status(layers)  # type: ignore[arg-type]
            assert cs.worst_check_status(statuses) == expected, statuses

    def test_record_outcome_is_noop_without_sink(self) -> None:
        cs.record_check_outcome(None, "naming_contract", cs.CHECK_ERROR, "whatever")
        sink: list[dict[str, Any]] = []
        cs.record_check_outcome(sink, "naming_contract", cs.CHECK_OK)
        assert sink == [{"check": "naming_contract", "status": "ok", "reason": ""}]


# ═══ 2. 可解析性判定：ValueError 也算读不懂；与 BH 私有实现等价 ═════════════


class TestParsabilityOracle:
    def test_syntax_error_inputs_are_unparseable(self) -> None:
        for code in (_BROKEN, _PY2_PRINT, _BROKEN_PATCHED):
            assert cs.parses_as_module(code) is False, code

    def test_value_error_subclass_is_unparseable(self) -> None:
        """孤立代理位 ⇒ ast.parse 抛 UnicodeEncodeError（ValueError 子类）。"""
        with pytest.raises(UnicodeEncodeError):
            ast.parse(_BLIND_VALUE)
        assert cs.parses_as_module(_BLIND_VALUE) is False
        assert cs.unparseable_side(_CLEAN, _BLIND_VALUE) == cs.UNPARSEABLE_PATCHED

    def test_null_byte_is_syntax_error_not_value_error(self) -> None:
        """当场核实并锁定：3.14.6 上空字节归 SyntaxError（docstring 里那句勘误的依据）。"""
        with pytest.raises(SyntaxError):
            ast.parse("x = 1\x00\n")
        assert cs.parses_as_module("x = 1\x00\n") is False

    def test_empty_source_parses(self) -> None:
        assert cs.parses_as_module("") is True

    def test_original_side_takes_precedence(self) -> None:
        """两侧都读不懂时报原始侧：没有基准符号集就谈不上比较补丁。"""
        assert cs.unparseable_side(_BROKEN, _BROKEN_PATCHED) == cs.UNPARSEABLE_ORIGINAL
        assert cs.unparseable_side(_CLEAN, _BROKEN_PATCHED) == cs.UNPARSEABLE_PATCHED
        assert cs.unparseable_side(_CLEAN, _WITH_CONST) is None

    def test_equivalence_with_testless_private_helper(self) -> None:
        """BH 的 `_unparseable_side` 与 BI 的共享实现逐输入等价（不改变 BH 代码）。"""
        corpus = [
            (_CLEAN, _WITH_CONST),
            (_BROKEN, _CLEAN),
            (_CLEAN, _BROKEN),
            (_BROKEN, _BROKEN_PATCHED),
            (_NO_SYMBOLS, _CLEAN),
            (_CLEAN, _BLIND_VALUE),
            (_BLIND_VALUE, _CLEAN),
            ("", _CLEAN),
            (_CLEAN, ""),
        ]
        for original, patched in corpus:
            assert cs.unparseable_side(original, patched) == tv._unparseable_side(original, patched), (
                original,
                patched,
            )


# ═══ 3. 危险 API 守卫：判定值不变 + 三态披露 ═══════════════════════════════


class TestDangerousApiGuardStatus:
    def test_judgment_invariance_over_corpus(self) -> None:
        """返回值与改前公式逐条相同（本文件最重要的一条锁）。"""
        corpus = [
            (_CLEAN, _WITH_CONST),
            (_CLEAN, _PATCH_DANGEROUS),
            (_ORIG_HAS_OS, _PATCH_DANGEROUS),
            (_BROKEN, _PATCH_DANGEROUS),
            (_CLEAN, _BROKEN_PATCHED),
            ("", _CLEAN),
            (_CLEAN, ""),
            (_BLIND_VALUE, _CLEAN),
            (_CLEAN, _BLIND_VALUE),
        ]
        for original, patched in corpus:
            sink: list[dict[str, Any]] = []
            assert pa_mod.dangerous_api_added(original, patched, outcome_sink=sink) == _old_dangerous_api_added(
                original, patched
            ), (original, patched)

    def test_measurable_and_clean(self) -> None:
        sink: list[dict[str, Any]] = []
        added = pa_mod.dangerous_api_added(_CLEAN, _WITH_CONST, outcome_sink=sink)
        assert added == []
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_OK, "")

    def test_measurable_and_blocking(self) -> None:
        sink: list[dict[str, Any]] = []
        added = pa_mod.dangerous_api_added(_CLEAN, _PATCH_DANGEROUS, outcome_sink=sink)
        assert "os.system" in added
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_OK, "")

    def test_existing_dangerous_call_not_counted_as_new(self) -> None:
        """差集口径：原代码已有的危险调用仍不算新增，且这属于"测量成功"。"""
        sink: list[dict[str, Any]] = []
        assert pa_mod.dangerous_api_added(_ORIG_HAS_OS, _PATCH_DANGEROUS, outcome_sink=sink) == []
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_OK, "")

    def test_patched_side_blind_is_fail_open_and_disclosed(self) -> None:
        """改前的静默 fail-open：差集恒空 ⇒ 放行，现在必须点名 error。"""
        sink: list[dict[str, Any]] = []
        added = pa_mod.dangerous_api_added(_CLEAN, "import os\n\n\ndef f(:\n    os.system('ls')\n", outcome_sink=sink)
        assert added == []  # 判定值不变（放行）
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_ERROR, cs.UNPARSEABLE_PATCHED)

    def test_original_side_blind_keeps_conservative_over_block(self) -> None:
        """保守侧口径不变：基准读不懂 ⇒ 补丁的全部危险命中都算"新增"。"""
        sink: list[dict[str, Any]] = []
        added = pa_mod.dangerous_api_added(_BROKEN, _PATCH_DANGEROUS, outcome_sink=sink)
        assert "os.system" in added
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_ERROR, cs.UNPARSEABLE_ORIGINAL)

    def test_empty_input_is_disabled_not_ok(self) -> None:
        """开关关/空输入 ⇒ disabled：不得与"跑完且零新增"共用一个空列表读数。"""
        for original, patched in (("", _CLEAN), (_CLEAN, ""), ("", "")):
            sink: list[dict[str, Any]] = []
            assert pa_mod.dangerous_api_added(original, patched, outcome_sink=sink) == []
            assert _sink_status(sink, "dangerous_api") == (cs.CHECK_DISABLED, "empty_input")

    def test_sink_optional_zero_overhead(self) -> None:
        assert pa_mod.dangerous_api_added(_CLEAN, _PATCH_DANGEROUS) == _old_dangerous_api_added(
            _CLEAN, _PATCH_DANGEROUS
        )


# ═══ 4. 命名契约守卫：四义 (True, []) 拆成三态 ═════════════════════════════


class TestNamingContractStatus:
    def test_judgment_invariance_over_corpus(self) -> None:
        corpus = [
            (_CLEAN, _WITH_CONST),
            (_WITH_CONST, _PATCH_DROP_CONST),
            (_BROKEN, _CLEAN),
            (_BROKEN, _PATCH_DROP_CONST),
            (_WITH_CONST, _BROKEN_PATCHED),
            (_NO_SYMBOLS, _BROKEN_PATCHED),
            (_NO_SYMBOLS, _CLEAN),
            ("", _CLEAN),
            (_CLEAN, ""),
            (_BLIND_VALUE, _CLEAN),
        ]
        for original, patched in corpus:
            sink: list[dict[str, Any]] = []
            assert pa_mod.check_naming_contract(original, patched, outcome_sink=sink) == _old_check_naming_contract(
                original, patched
            ), (original, patched)

    def test_measured_pass(self) -> None:
        sink: list[dict[str, Any]] = []
        ok, missing = pa_mod.check_naming_contract(_WITH_CONST, _WITH_CONST, outcome_sink=sink)
        assert (ok, missing) == (True, [])
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_OK, "")

    def test_measured_rejection_is_ok_status(self) -> None:
        """真拒绝 ≠ 不可测量：守卫跑完了，结论就是"补丁删了符号"。"""
        sink: list[dict[str, Any]] = []
        ok, missing = pa_mod.check_naming_contract(_WITH_CONST, _PATCH_DROP_CONST, outcome_sink=sink)
        assert (ok, missing) == (False, ["CONST"])
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_OK, "")

    def test_original_blind_passes_but_disclosed(self) -> None:
        sink: list[dict[str, Any]] = []
        ok, missing = pa_mod.check_naming_contract(_PY2_PRINT, _CLEAN, outcome_sink=sink)
        assert (ok, missing) == (True, [])  # 保守放行口径不变
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_ERROR, cs.UNPARSEABLE_ORIGINAL)

    def test_patched_blind_with_symbols_rejects_without_misattribution(self, caplog: pytest.LogCaptureFixture) -> None:
        """误归因收口：补丁从未解析成 AST，不得说成"补丁删除了 N 个符号"。"""
        with caplog.at_level(logging.WARNING, logger="src.tools.patch_applier"):
            sink: list[dict[str, Any]] = []
            ok, missing = pa_mod.check_naming_contract(_WITH_CONST, _BROKEN_PATCHED, outcome_sink=sink)
        assert (ok, missing) == (False, ["CONST", "f"])  # 保守拒绝口径不变
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_ERROR, cs.UNPARSEABLE_PATCHED)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "无法确认仍存在" in text
        assert "补丁删除了" not in text

    def test_original_blind_warning_says_no_comparison_made(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.tools.patch_applier"):
            pa_mod.check_naming_contract(_BROKEN, _CLEAN)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "未做任何符号比较" in text
        assert "命名契约检查失败" not in text

    def test_no_module_level_symbols_is_measured_pass(self) -> None:
        """原文可解析但确实没有模块级符号 ⇒ 这是"量过、无可删之物"，不是没量。"""
        sink: list[dict[str, Any]] = []
        ok, _ = pa_mod.check_naming_contract(_NO_SYMBOLS, _CLEAN, outcome_sink=sink)
        assert ok is True
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_OK, "no_module_level_symbols")

    def test_patched_blind_and_no_original_symbols_is_error(self) -> None:
        sink: list[dict[str, Any]] = []
        ok, _ = pa_mod.check_naming_contract(_NO_SYMBOLS, _BROKEN_PATCHED, outcome_sink=sink)
        assert ok is True
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_ERROR, cs.UNPARSEABLE_PATCHED)

    def test_switch_off_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATCH_CONTRACT_CHECK", "false")
        sink: list[dict[str, Any]] = []
        ok, missing = pa_mod.check_naming_contract(_WITH_CONST, _PATCH_DROP_CONST, outcome_sink=sink)
        assert (ok, missing) == (True, [])  # 恒放行口径不变
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_DISABLED, "patch_contract_check_disabled")

    def test_empty_input_is_disabled(self) -> None:
        sink: list[dict[str, Any]] = []
        assert pa_mod.check_naming_contract("", _CLEAN, outcome_sink=sink) == (True, [])
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_DISABLED, "empty_input")

    def test_sink_optional_keeps_return_contract(self) -> None:
        assert pa_mod.check_naming_contract(_WITH_CONST, _PATCH_DROP_CONST) == (False, ["CONST"])


# ═══ 5. _check_patch_safety：生产形状 A/B/C/D 的状态聚合 ════════════════════


def _run_node(state: dict[str, Any]) -> dict[str, Any]:
    """跑真实 `_patch_applier_node`（只屏蔽 trace/事件发布，守卫全程为真）。"""
    with (
        patch.object(nodes_mod, "_trace_node"),
        patch.object(nodes_mod, "publish_patch_applied"),
    ):
        return nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]


def _safety_state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {"target_code": _CLEAN, "iteration": 0}
    state.update(extra)
    return state


class TestCheckPatchSafetyOutcomes:
    def test_shape_a_original_blind_is_error(self) -> None:
        """A：原文读不懂 + 合法补丁 ⇒ 判定仍是放行，状态必须点名 error。"""
        state = _safety_state()
        applied, new_code = nodes_mod._check_patch_safety(  # type: ignore[arg-type]
            state, _PY2_PRINT, "def f():\n    return 2\n", True
        )
        assert applied is True
        assert new_code == "def f():\n    return 2\n"
        outcomes = state["_bi_safety_outcomes"]
        assert [o["check"] for o in outcomes] == ["naming_contract", "dangerous_api"]
        assert all(o["status"] == cs.CHECK_ERROR for o in outcomes)
        assert all(o["reason"] == cs.UNPARSEABLE_ORIGINAL for o in outcomes)

    def test_shape_b_patched_blind_rejects_and_discloses(self) -> None:
        """B：补丁读不懂 ⇒ 保守拒绝 + 两侧状态均为 error（不再谎称删除符号）。"""
        state = _safety_state()
        applied, new_code = nodes_mod._check_patch_safety(  # type: ignore[arg-type]
            state, _WITH_CONST, _BROKEN_PATCHED, True
        )
        assert applied is False
        assert new_code == _WITH_CONST
        sink = state["_bi_safety_outcomes"]
        assert _sink_status(sink, "naming_contract") == (cs.CHECK_ERROR, cs.UNPARSEABLE_PATCHED)
        assert _sink_status(sink, "dangerous_api") == (cs.CHECK_ERROR, cs.UNPARSEABLE_PATCHED)

    def test_shape_c_clean_patch_is_all_ok_without_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.nodes"):
            state = _safety_state()
            applied, new_code = nodes_mod._check_patch_safety(  # type: ignore[arg-type]
                state, _WITH_CONST, _WITH_CONST_2, True
            )
        assert applied is True
        assert new_code == _WITH_CONST_2
        assert cs.worst_check_status([o["status"] for o in state["_bi_safety_outcomes"]]) == cs.CHECK_OK
        assert "可测量性降级" not in "\n".join(r.getMessage() for r in caplog.records)

    def test_shape_d_noop_when_patch_not_applied(self) -> None:
        """D：本轮没做预检 ⇒ 不写临时键（通道键保持 None = 未执行，非"通过"）。"""
        state = _safety_state()
        applied, _new_code = nodes_mod._check_patch_safety(  # type: ignore[arg-type]
            state, _WITH_CONST, _WITH_CONST, False
        )
        assert applied is False
        assert "_bi_safety_outcomes" not in state

    def test_independent_checks_aggregate_as_worst(self) -> None:
        """独立两层 ⇒ 最差者优先：契约 ok + 危险 API error ⇒ 整体 error。"""
        assert cs.worst_check_status([cs.CHECK_OK, cs.CHECK_ERROR]) == cs.CHECK_ERROR
        assert cs.worst_check_status([cs.CHECK_OK, cs.CHECK_OK]) == cs.CHECK_OK
        assert cs.worst_check_status([]) == cs.CHECK_ERROR

    def test_downgrade_warning_names_every_check(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.nodes"):
            nodes_mod._check_patch_safety(  # type: ignore[arg-type]
                _safety_state(), _BROKEN, _PATCH_DANGEROUS, True
            )
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "写盘前静态预检可测量性降级（整体 status=error）" in text
        assert "naming_contract=error:unparseable_original" in text
        assert "dangerous_api=error:unparseable_original" in text


# ═══ 6. state 通道：声明 + 真实节点端到端 ═══════════════════════════════════


class TestStateChannel:
    def test_keys_declared_in_typeddict(self) -> None:
        hints = AITesterState.__annotations__
        assert "safety_check_status" in hints
        assert "safety_check_outcomes" in hints

    def test_initial_state_defaults_none(self) -> None:
        state = create_initial_state(
            task_uuid="bi-lock",
            target_file="mod.py",
            target_code=_CLEAN,
            max_iterations=1,
        )
        assert state["safety_check_status"] is None  # type: ignore[typeddict-item]
        assert state["safety_check_outcomes"] is None  # type: ignore[typeddict-item]

    def test_node_publishes_channel_on_blind_original(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端（真实守卫、零 mock）：原文 py2 ⇒ 补丁照样写盘，但读数点名不可测量。"""
        target = tmp_path / "mod.py"
        original = _PY2_PRINT
        target.write_text(original, encoding="utf-8")
        state: dict[str, Any] = {
            "target_code": original,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
            "error_category": "RUNTIME",
            "diagnosis": "x",
        }
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        update = _run_node(state)
        assert update["safety_check_status"] == cs.CHECK_ERROR
        assert {o["check"] for o in update["safety_check_outcomes"]} == {"naming_contract", "dangerous_api"}
        # 判定侧不变：契约从未比较 ⇒ 不产生"缺失符号"读数
        assert update.get("contract_missing_symbols") in (None, [])

    def test_channel_absent_when_prechecks_not_run(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """空补丁 ⇒ 本轮未做预检：两键不写（LangGraph 保持 None），不得凭空造 "ok"。"""
        target = tmp_path / "mod.py"
        target.write_text(_CLEAN, encoding="utf-8")
        state: dict[str, Any] = {
            "target_code": _CLEAN,
            "patch": _CLEAN,
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
            "error_category": "RUNTIME",
            "diagnosis": "x",
        }
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        update = _run_node(state)
        assert "safety_check_status" not in update
        assert "safety_check_outcomes" not in update


# ═══ 7. type_repair 契约回环的消费侧披露 ═══════════════════════════════════


class TestTypeRepairContractDisclosure:
    def test_defaults_are_disabled_not_ok(self) -> None:
        """无疑点 ⇒ 早退，从未做符号比较：contract_ok=True 必须配 disabled 披露。"""
        out = tr.type_repair_layer(_CLEAN, _CLEAN)
        assert out["contract_ok"] is True
        assert out["contract_status"] == cs.CHECK_DISABLED
        assert out["contract_reason"] == "contract_not_evaluated"
        assert out["contract_outcomes"] == []

    def test_enforcement_off_is_disabled_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        out = tr.type_repair_layer(
            _WITH_CONST,
            "def f() -> int:\n    return helper()\n\n\nCONST = 3\n",
            llm_repair=lambda q, o, p: _WITH_CONST,
            enforce_contract=False,
        )
        assert out["repaired"] is True
        assert out["contract_ok"] is True
        assert out["contract_status"] == cs.CHECK_DISABLED
        assert out["contract_reason"] == "contract_enforcement_disabled"

    def test_measured_pass_reports_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        out = tr.type_repair_layer(
            _WITH_CONST,
            "def f() -> int:\n    return helper()\n\n\nCONST = 3\n",
            llm_repair=lambda q, o, p: _WITH_CONST,
        )
        assert out["contract_ok"] is True
        assert out["contract_status"] == cs.CHECK_OK
        assert out["contract_reason"] == ""
        assert [o["check"] for o in out["contract_outcomes"]] == ["naming_contract"]

    def test_measured_rejection_keeps_ok_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """契约真被破坏 ⇒ status 仍是 ok（量出来了），判定值与历史一致。"""
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        out = tr.type_repair_layer(
            _WITH_CONST,
            "def f() -> int:\n    return helper()\n\n\nCONST = 3\n",
            llm_repair=lambda q, o, p: _CLEAN,  # 修订删掉了 CONST
        )
        assert out["repaired"] is False
        assert out["contract_ok"] is False
        assert out["contract_status"] == cs.CHECK_OK
        assert out["missing_symbols"] == ["CONST"]

    def test_blind_reference_is_disclosed_while_judgment_holds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """参照侧读不懂 ⇒ 修订被接受（口径不变），但 contract_status=error 点名。"""
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        out = tr.type_repair_layer(
            _WITH_CONST,
            "def f() -> int:\n    return helper()\n\n\nCONST = 3\n",
            llm_repair=lambda q, o, p: _CLEAN,
            enforce_contract_ref=_BROKEN,
        )
        assert out["repaired"] is True
        assert out["contract_ok"] is True
        assert out["contract_status"] == cs.CHECK_ERROR
        assert out["contract_reason"] == cs.UNPARSEABLE_ORIGINAL

    def test_guard_exception_is_error_and_still_conservative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        with monkeypatch.context() as m:
            m.setattr(pa_mod, "check_naming_contract", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
            out = tr.type_repair_layer(
                _WITH_CONST,
                "def f() -> int:\n    return helper()\n\n\nCONST = 3\n",
                llm_repair=lambda q, o, p: _WITH_CONST,
            )
        assert out["repaired"] is False  # 保守保留原补丁（判定值不变）
        assert out["contract_ok"] is True  # 改前也是 True：异常路径从未比较
        assert out["contract_status"] == cs.CHECK_ERROR
        assert out["contract_reason"] == "contract_check_exception"

    def test_static_check_keys_unchanged(self) -> None:
        """BG 的键不受影响（同一次调用两套披露并存）。"""
        out = tr.type_repair_layer(_CLEAN, _CLEAN)
        assert out["static_check_status"] == tr.STATIC_CHECK_DISABLED
        assert out["static_check_outcomes"], "BG 口径下 disabled 也逐条留痕"
        assert all(o["status"] == tr.STATIC_CHECK_DISABLED for o in out["static_check_outcomes"])


def test_safe_apply_patch_still_rolls_back_on_new_dangerous_api() -> None:
    """边界锁：`PATCH_DANGEROUS_API_GUARD` 只管 `safe_apply_patch`，本轮未动其判定。"""
    written, ok = pa_mod.safe_apply_patch(_CLEAN, _PATCH_DANGEROUS)
    assert ok is False
    assert written == _CLEAN
