"""BJ（2026-10-22）：AST 断言一致性检查的「读不懂 ⇒ 无疑点」收口锁。

缺陷族（F03 静态侧，与 BD–BI 的 `rc==0` 判绿 / 写盘前预检同族，落在
Generator 产出后的 `oracle_validator.check_assertions` 上）。改前实测
（Python 3.14.6，零 LLM，`git show HEAD:src/tools/oracle_validator.py` 直调）：

1. **四义 `[]`**：`check_assertions` 的空疑点列表同时表示"扫过且无疑点"、
   "输入为空"、"测试文本读不懂（从未扫描）"，加上被测侧的"读不懂 ⇒ 类型推断
   通道静默失效"。语料 `scripts/tools/bj_corpus_probe.py`：10855 条
   `generated_test` 中 153 条走盲区（77 空 + 72 围栏 + 4 真语法错误）。
2. **O4 强制重生成对盲区永不触发**：唯一消费点 `_run_generator_postchecks`
   把 `[]` 读成 `tautological_count = 0`，故"恒真断言 ⇒ 标记 test_defect ⇒
   路由回 generator 重生成"这条唯一的写侧路径对读不懂的产物恒假（开关开启的
   57 份归档里实测有 1 个盲区站点，`benchmark_quixbugs_20261017_201928.json`
   的围栏产物）。
3. **被测侧盲区伪装成"类型一致"**：`target_code` 读不懂时旧实现
   `except SyntaxError: pass`，类型推断表恒空 ⇒ `type_mismatch` 通道实际关闭，
   但读数上与"类型都一致"逐字节相同。
4. **异常抛穿**：只捕 `SyntaxError` ⇒ 孤立代理位文本（`UnicodeEncodeError`，
   `ValueError` 子类）从 `check_assertions` 抛穿进 Generator 节点（BH/BI 同型，
   本轮把解析面收敛到 `parses_as_module`）。

修复口径（**判定值与判定方向逐字节不变**，只补披露）：`check_assertions` 新增
可选 `outcome_sink`，逐腿追加 `{check, status, reason}`（词表取自
`src/utils/check_status.py` 单一事实源）；`_run_generator_postchecks` 做 worst-of
聚合并发布 `oracle_check_status` / `oracle_check_outcomes` 两个 state 通道键；
**不做围栏剥离**（那会把盲区变成疑点 ⇒ 改判定）。
"""

from __future__ import annotations

import ast
import logging
import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.tools.oracle_validator as ov
from src.graph import nodes as nodes_mod
from src.graph.state import AITesterState, create_initial_state
from src.utils import check_status as cs

# ─── 语料 ────────────────────────────────────────────────────────────────
_TARGET = "def f(a):\n    return 1\n"
_CLEAN_TEST = "def test_f():\n    assert f(1) == 1\n"
_TAUTO_TEST = "def test_f():\n    assert True\n"
_MAGIC_TEST = "def test_f():\n    assert f(1) == 4242\n"
_TYPE_TEST = 'def test_f():\n    assert f(1) == "s"\n'
_NO_ASSERT_TEST = "x = 1\n"
_EMPTY_TEST = ""
_BLANK_TEST = "   \n\t\n"
_BROKEN_TEST = "def f(:\n"
_FENCED_TEST = "```python\n" + _TAUTO_TEST + "```\n"
_FENCE_IN_BODY_TEST = 'def test_f():\n    msg = "```"\n    assert f(1\n'
_PY2_TARGET = 'print "x"\n\n\ndef f(a):\n    return 1\n'
_BLIND_VALUE_TEST = "x = '\ud800'\n"  # ast.parse 抛 UnicodeEncodeError（ValueError 子类）
_NULL_BYTE_TEST = "x = 1\x00\n"  # 3.14.6：SyntaxError（"cannot contain null bytes"）


def _legs(sink: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """把 sink 折成可比较的三元组序列（锁逐字取值，不看对象身份）。"""
    return [(o["check"], o["status"], o["reason"]) for o in sink]


def _check(test_code: str, target_code: str | None = None) -> tuple[list[dict[str, Any]], list[Any]]:
    sink: list[dict[str, Any]] = []
    findings = ov.check_assertions(test_code, target_code, outcome_sink=sink)
    return findings, _legs(sink)


# ─── §1 词表与单一事实源 ─────────────────────────────────────────────────


@pytest.mark.unit
class TestSharedVocabulary:
    def test_oracle_uses_check_status_constants_by_identity(self) -> None:
        assert ov.CHECK_OK is cs.CHECK_OK
        assert ov.CHECK_DISABLED is cs.CHECK_DISABLED
        assert ov.CHECK_ERROR is cs.CHECK_ERROR

    def test_oracle_has_no_own_status_literals(self) -> None:
        """本轮不新建第二套词表：oracle 模块里不得出现 status 裸字面量，只用导入常量。"""
        body = pathlib.Path(ov.__file__).with_suffix(".py").read_text(encoding="utf-8")
        for literal in ('"ok"', '"disabled"', '"error"', '"unavailable"'):
            assert literal not in body, f"oracle_validator 里出现了本地字面量 {literal}"

    def test_every_recorded_status_is_in_declared_vocabulary(self) -> None:
        corpus = [_CLEAN_TEST, _NO_ASSERT_TEST, _EMPTY_TEST, _BROKEN_TEST, _FENCED_TEST]
        for test_code in corpus:
            for target in (None, _TARGET, _BROKEN_TEST):
                _found, legs = _check(test_code, target)
                for _check_name, status, _reason in legs:
                    assert status in cs.CHECK_STATUS_VOCABULARY

    def test_parsability_face_is_shared(self) -> None:
        """盲区判定面与 BH/BI 同一函数：孤立代理位与空字节都算"读不懂"。"""
        assert cs.parses_as_module(_CLEAN_TEST) is True
        assert cs.parses_as_module(_BLIND_VALUE_TEST) is False
        assert cs.parses_as_module(_NULL_BYTE_TEST) is False


# ─── §2 测试侧腿（assertion_consistency）──────────────────────────────────


@pytest.mark.unit
class TestAssertionConsistencyLeg:
    def test_empty_string_is_disabled(self) -> None:
        findings, legs = _check(_EMPTY_TEST, _TARGET)
        assert findings == []
        assert legs == [("assertion_consistency", "disabled", "empty_input")]

    def test_blank_string_is_disabled(self) -> None:
        _found, legs = _check(_BLANK_TEST)
        assert legs == [("assertion_consistency", "disabled", "empty_input")]

    def test_fenced_block_is_error_fenced(self) -> None:
        findings, legs = _check(_FENCED_TEST, _TARGET)
        assert findings == []
        assert legs == [("assertion_consistency", "error", "unparseable_test:fenced_block")]

    def test_fence_only_in_body_is_error_syntax(self) -> None:
        """判据是"剥掉前导空白后以围栏开头"：正文中间的围栏不享传输层伪影待遇。"""
        _found, legs = _check(_FENCE_IN_BODY_TEST)
        assert legs == [("assertion_consistency", "error", "unparseable_test:syntax")]

    def test_plain_syntax_error_is_error_syntax(self) -> None:
        findings, legs = _check(_BROKEN_TEST, _TARGET)
        assert findings == []
        assert legs == [("assertion_consistency", "error", "unparseable_test:syntax")]

    def test_null_byte_is_error_not_crash(self) -> None:
        findings, legs = _check(_NULL_BYTE_TEST, _TARGET)
        assert findings == []
        assert legs == [("assertion_consistency", "error", "unparseable_test:syntax")]

    def test_lone_surrogate_no_longer_propagates(self) -> None:
        """本轮唯一披露的行为变化：ValueError 子类不再抛穿（与 BH/BI 同口径）。"""
        with pytest.raises(UnicodeEncodeError):
            ast.parse(_BLIND_VALUE_TEST)
        findings, legs = _check(_BLIND_VALUE_TEST, _TARGET)
        assert findings == []
        assert legs[0] == ("assertion_consistency", "error", "unparseable_test:syntax")

    def test_measured_test_with_asserts_is_ok_checked(self) -> None:
        findings, legs = _check(_TAUTO_TEST, _TARGET)
        assert [f["type"] for f in findings] == ["tautological"]
        assert legs[0] == ("assertion_consistency", "ok", "assertions_checked")

    def test_measured_test_without_asserts_is_ok_no_asserts(self) -> None:
        findings, legs = _check(_NO_ASSERT_TEST, _TARGET)
        assert findings == []
        assert legs[0] == ("assertion_consistency", "ok", "no_assert_statements")

    def test_sink_records_at_most_two_legs_in_fixed_order(self) -> None:
        _found, legs = _check(_CLEAN_TEST, _TARGET)
        assert [name for name, _s, _r in legs] == ["assertion_consistency", "target_type_inference"]

    def test_blind_test_records_only_first_leg(self) -> None:
        """盲区早退 ⇒ 第二条腿不记（没走到被测侧，记了就是假陈述）。"""
        for blind in (_EMPTY_TEST, _BROKEN_TEST, _FENCED_TEST):
            _found, legs = _check(blind, _TARGET)
            assert [name for name, _s, _r in legs] == ["assertion_consistency"]

    def test_sink_optional_is_zero_cost(self) -> None:
        assert ov.check_assertions(_TAUTO_TEST, _TARGET) == ov.check_assertions(_TAUTO_TEST, _TARGET, None)
        assert ov.check_assertions(_BROKEN_TEST, _TARGET, None) == []


# ─── §3 被测侧腿（target_type_inference）─────────────────────────────────


@pytest.mark.unit
class TestTargetLeg:
    def test_target_absent_is_disabled(self) -> None:
        _found, legs = _check(_CLEAN_TEST, None)
        assert legs == [
            ("assertion_consistency", "ok", "assertions_checked"),
            ("target_type_inference", "disabled", "target_not_provided"),
        ]

    def test_target_empty_string_is_disabled(self) -> None:
        _found, legs = _check(_CLEAN_TEST, "")
        assert legs[1] == ("target_type_inference", "disabled", "target_not_provided")

    def test_target_parsable_is_ok(self) -> None:
        _found, legs = _check(_TYPE_TEST, _TARGET)
        assert legs[1] == ("target_type_inference", "ok", "target_parsed")

    def test_target_syntax_error_is_error(self) -> None:
        _found, legs = _check(_TYPE_TEST, _BROKEN_TEST)
        assert legs[1] == ("target_type_inference", "error", "unparseable_target")

    def test_py2_target_is_error(self) -> None:
        _found, legs = _check(_TYPE_TEST, _PY2_TARGET)
        assert legs[1] == ("target_type_inference", "error", "unparseable_target")

    def test_lone_surrogate_target_no_longer_propagates(self) -> None:
        findings, legs = _check(_CLEAN_TEST, _BLIND_VALUE_TEST)
        assert findings == []
        assert legs[1] == ("target_type_inference", "error", "unparseable_target")

    def test_blank_but_nonempty_target_counts_as_parsed(self) -> None:
        """`"   "` 能被 ast.parse 读成空模块 ⇒ ok（读过了，只是没有函数可推断）。"""
        _found, legs = _check(_CLEAN_TEST, "   ")
        assert legs[1] == ("target_type_inference", "ok", "target_parsed")

    def test_both_legs_recorded_even_when_target_blind(self) -> None:
        _found, legs = _check(_TAUTO_TEST, _BROKEN_TEST)
        assert len(legs) == 2


# ─── §4 判定不变性（承诺"只补披露"）──────────────────────────────────────


@pytest.mark.unit
class TestJudgmentInvariance:
    @pytest.mark.parametrize(
        ("test_code", "target_code"),
        [
            (_EMPTY_TEST, _TARGET),
            (_BLANK_TEST, _TARGET),
            (_BROKEN_TEST, _TARGET),
            (_FENCED_TEST, _TARGET),
            (_NULL_BYTE_TEST, _TARGET),
            (_BLIND_VALUE_TEST, _TARGET),
            (_CLEAN_TEST, _BROKEN_TEST),
            (_CLEAN_TEST, None),
        ],
    )
    def test_blind_and_ok_legs_all_return_empty_list(self, test_code: str, target_code: str | None) -> None:
        """盲区与"真干净"返回同一个 `[]`：本轮**没有**把披露混进判定值。"""
        assert ov.check_assertions(test_code, target_code) == []

    def test_no_fence_stripping(self) -> None:
        """剥离围栏会让块内的 `assert True` 变成疑点 ⇒ 那是改判定，本轮明确不做。"""
        assert ov.check_assertions(_FENCED_TEST, _TARGET) == []
        stripped = _FENCED_TEST.replace("```python\n", "").replace("```\n", "")
        assert len(ov.check_assertions(stripped, _TARGET)) == 1  # 证明"如果剥离就会改判"

    @pytest.mark.parametrize("test_code", [_TAUTO_TEST, _MAGIC_TEST, _TYPE_TEST, _NO_ASSERT_TEST])
    def test_findings_identical_with_and_without_sink(self, test_code: str) -> None:
        assert ov.check_assertions(test_code, _TARGET) == ov.check_assertions(test_code, _TARGET, outcome_sink=[])

    def test_three_finding_types_still_detected(self) -> None:
        types = {
            "tautological": _TAUTO_TEST,
            "magic_number": _MAGIC_TEST,
            "type_mismatch": _TYPE_TEST,
        }
        for expected, test_code in types.items():
            found = ov.check_assertions(test_code, _TARGET)
            assert expected in {f["type"] for f in found}, expected

    def test_target_blind_still_suppresses_type_mismatch(self) -> None:
        """旧口径不变：被测侧读不懂 ⇒ type_mismatch 通道哑火（现在是 error 而非沉默）。"""
        assert ov.check_assertions(_TYPE_TEST, _BROKEN_TEST) == []

    def test_ok_status_is_the_only_evidence_of_no_findings(self) -> None:
        """两条腿都 ok 且 findings 为空 ⇒ "无疑点"；其余组合一律不构成该证据。"""
        clean, sink = _check(_NO_ASSERT_TEST, _TARGET)
        assert clean == [] and [s for _c, s, _r in sink] == ["ok", "ok"]
        blind, sink = _check(_FENCED_TEST, _TARGET)
        assert blind == [] and [s for _c, s, _r in sink] == ["error"]

    def test_return_type_still_list_of_dicts(self) -> None:
        found = ov.check_assertions(_TAUTO_TEST, _TARGET, outcome_sink=[])
        assert isinstance(found, list) and all(isinstance(f, dict) for f in found)


# ─── §5 消费侧 `_run_generator_postchecks` ───────────────────────────────


def _state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "target_file": "target_mod.py",
        "module_name": "target_mod",
        "target_code": _TARGET,
        "target_function": "f",
        "test_plan": {},
        "iteration": 0,
        "max_iterations": 3,
    }
    state.update(extra)
    return state


def _neutral_legs(monkeypatch: pytest.MonkeyPatch) -> None:
    """把与本轮无关的两条后腿（N5 去重 / R1c 规约注入）固定为恒等，隔离观测面。"""
    monkeypatch.setattr(nodes_mod, "_apply_test_suite_dedup", lambda code: (code, 0))
    monkeypatch.setattr(nodes_mod, "_spec_oracle_injection_verdict", lambda code, _s: (code, None, "not_attempted"))


def _post(monkeypatch: pytest.MonkeyPatch, code: str, *, enabled: bool, **extra: Any) -> dict[str, Any]:
    monkeypatch.setattr(nodes_mod, "_oracle_validate_enabled", lambda: enabled)
    _neutral_legs(monkeypatch)
    return nodes_mod._run_generator_postchecks(_state(**extra), code)  # type: ignore[arg-type]


@pytest.mark.unit
class TestGeneratorPostchecks:
    def test_switch_off_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(monkeypatch, _FENCED_TEST, enabled=False)
        assert result["oracle_check_status"] == "disabled"
        assert result["oracle_check_outcomes"] == [
            {"check": "assertion_consistency", "status": "disabled", "reason": "oracle_validate_disabled"}
        ]
        assert result["oracle_findings"] == []

    def test_no_generated_content_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(monkeypatch, "", enabled=True)
        assert result["oracle_check_status"] == "disabled"
        assert result["oracle_check_outcomes"][0]["reason"] == "no_generated_test"

    def test_fenced_product_is_error_and_no_o4(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """盲区主证：读不懂的产物在旧口径里=零恒真断言 ⇒ O4 恒不触发（判定仍如此，但可见）。"""
        result = _post(monkeypatch, _FENCED_TEST, enabled=True)
        assert result["oracle_check_status"] == "error"
        assert result["oracle_check_outcomes"][0]["reason"] == "unparseable_test:fenced_block"
        assert result["oracle_findings"] == []
        assert result["tautological_count"] == 0
        assert result["o4_triggered"] is False

    def test_measured_clean_is_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(monkeypatch, _CLEAN_TEST, enabled=True)
        assert result["oracle_check_status"] == "ok"
        assert len(result["oracle_check_outcomes"]) == 2

    def test_measured_tautology_still_fires_o4(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """判定不变：恒真断言照旧 count=1 且触发重生成，新增的只是 status。"""
        result = _post(monkeypatch, _TAUTO_TEST, enabled=True)
        assert result["oracle_check_status"] == "ok"
        assert result["tautological_count"] == 1
        assert result["o4_triggered"] is True

    def test_blind_target_degrades_aggregate_to_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """独立两腿 ⇒ 最差者优先：被测侧读不懂把整体拉成 error，但疑点照旧产出。"""
        result = _post(monkeypatch, _TAUTO_TEST, enabled=True, target_code=_BROKEN_TEST)
        assert result["oracle_check_status"] == "error"
        assert result["oracle_findings"]
        assert result["tautological_count"] == 1
        assert result["o4_triggered"] is True

    def test_disabled_leg_outranks_ok_leg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """worst-of 次序实测：disabled（未提供被测码）压过 ok（断言扫过了）。"""
        result = _post(monkeypatch, _CLEAN_TEST, enabled=True, target_code="")
        assert result["oracle_check_status"] == "disabled"
        assert [o["status"] for o in result["oracle_check_outcomes"]] == ["ok", "disabled"]

    def test_regeneration_cap_keeps_judgment_and_disclosure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(
            monkeypatch,
            _TAUTO_TEST,
            enabled=True,
            regeneration_count=nodes_mod.MAX_REGENERATIONS,
        )
        assert result["o4_triggered"] is False  # 上限保护不变
        assert result["oracle_check_status"] == "ok"

    def test_return_key_set_is_fixed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(monkeypatch, _CLEAN_TEST, enabled=True)
        assert set(result) == {
            "generated_test",
            "oracle_findings",
            "oracle_check_status",
            "oracle_check_outcomes",
            "deterministic_guard_report",
            "tautological_count",
            "o4_triggered",
            "spec_oracle_injected",
            "spec_oracle_verdict",
        }

    def test_generated_test_byte_identical_on_blind_product(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _post(monkeypatch, _FENCED_TEST, enabled=True)
        assert result["generated_test"] == _FENCED_TEST

    def test_outcomes_list_is_a_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """返回的 outcomes 不是内部 sink：外部改动不能污染下一轮。"""
        result = _post(monkeypatch, _CLEAN_TEST, enabled=True)
        result["oracle_check_outcomes"].append({"check": "x", "status": "ok", "reason": ""})
        again = _post(monkeypatch, _CLEAN_TEST, enabled=True)
        assert len(again["oracle_check_outcomes"]) == 2

    def test_aggregation_direction_is_worst_not_any_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """与 BG 的"任一后端 ok ⇒ ok"相反：本轮两腿独立，任一腿不可测量 ⇒ 整体不可测量。"""
        assert cs.worst_check_status(["ok", "error"]) == "error"
        assert cs.any_measurable_status(["ok", "error"]) == "ok"
        result = _post(monkeypatch, _TAUTO_TEST, enabled=True, target_code=_BROKEN_TEST)
        assert result["oracle_check_status"] == cs.worst_check_status(
            o["status"] for o in result["oracle_check_outcomes"]
        )


# ─── §6 通道发布（`_generator_node`）─────────────────────────────────────


def _run_generator(
    monkeypatch: pytest.MonkeyPatch,
    state: dict[str, Any],
    *,
    generate_return: str,
    **env: str,
) -> dict[str, Any]:
    agent = MagicMock()
    agent.generate.return_value = generate_return
    agent.generate_repro_test.return_value = "def test_repro():\n    assert f([]) == []\n"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with (
        patch.object(nodes_mod, "get_or_create_agent", return_value=agent),
        patch.object(nodes_mod, "ENABLE_RAG", False),
        patch.object(nodes_mod, "_trace_node"),
    ):
        return nodes_mod._generator_node(state)  # type: ignore[arg-type]


@pytest.mark.unit
class TestGeneratorNodeChannel:
    def test_default_off_publishes_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        update = _run_generator(monkeypatch, _state(), generate_return=_TAUTO_TEST)
        assert update["oracle_check_status"] == "disabled"
        assert update["oracle_check_outcomes"][0]["reason"] == "oracle_validate_disabled"
        assert "oracle_findings" not in update  # 旧口径：无疑点键不写

    def test_enabled_blind_publishes_error_without_findings_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        update = _run_generator(
            monkeypatch,
            _state(),
            generate_return=_FENCED_TEST,
            ORACLE_VALIDATE_ENABLE="true",
        )
        assert update["oracle_check_status"] == "error"
        assert "oracle_findings" not in update
        assert "defect_type" not in update  # 判定仍是"不触发 O4"

    def test_enabled_clean_publishes_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        update = _run_generator(
            monkeypatch,
            _state(),
            generate_return=_CLEAN_TEST,
            ORACLE_VALIDATE_ENABLE="true",
        )
        assert update["oracle_check_status"] == "ok"
        assert "oracle_findings" not in update

    def test_enabled_tautology_keeps_findings_and_o4(self, monkeypatch: pytest.MonkeyPatch) -> None:
        update = _run_generator(
            monkeypatch,
            _state(),
            generate_return=_TAUTO_TEST,
            ORACLE_VALIDATE_ENABLE="true",
        )
        assert {f["type"] for f in update["oracle_findings"]} == {"tautological"}
        assert update["oracle_check_status"] == "ok"
        assert update["defect_type"] == "test_defect"

    def test_degradation_warning_names_each_leg(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.nodes"):
            _post(monkeypatch, _FENCED_TEST, enabled=True)
        messages = [r.getMessage() for r in caplog.records if "断言一致性检查不可测量" in r.getMessage()]
        assert len(messages) == 1
        assert "assertion_consistency=error:unparseable_test:fenced_block" in messages[0]

    def test_no_warning_when_measured(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.nodes"):
            _post(monkeypatch, _CLEAN_TEST, enabled=True)
        assert not [r for r in caplog.records if "断言一致性检查不可测量" in r.getMessage()]

    def test_target_blind_warning_mentions_target_leg(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="src.graph.nodes"):
            _post(monkeypatch, _TAUTO_TEST, enabled=True, target_code=_BROKEN_TEST)
        messages = [r.getMessage() for r in caplog.records if "断言一致性检查不可测量" in r.getMessage()]
        assert len(messages) == 1
        assert "target_type_inference=error:unparseable_target" in messages[0]


# ─── §7 state 通道声明与默认值 ────────────────────────────────────────────


@pytest.mark.unit
class TestStateChannel:
    def test_keys_declared_in_typeddict(self) -> None:
        annotations = AITesterState.__annotations__
        assert "oracle_check_status" in annotations
        assert "oracle_check_outcomes" in annotations

    def test_initial_state_defaults_none(self) -> None:
        state = create_initial_state(
            task_uuid="t-bj",
            target_file="target_mod.py",
            target_code=_TARGET,
            max_iterations=3,
        )
        assert state["oracle_check_status"] is None
        assert state["oracle_check_outcomes"] is None

    def test_channel_names_do_not_collide_with_spec_oracle_field(self) -> None:
        """实验侧 `oracle_status`（= task["oracle"]["status"]，规约 oracle 臂）是另一回事。"""
        assert "oracle_status" not in AITesterState.__annotations__
        assert "oracle_check_status" in AITesterState.__annotations__
