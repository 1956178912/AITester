"""BK（2026-10-22）：``ast.parse`` 守卫的捕获面与形态归因锁。

缺陷族（F03 静态侧第八个消费面）：``src/`` 78 个含 ``ast.parse`` 的 ``try`` 站点里
未收敛前 35 个只捕 ``SyntaxError``（本仓棘轮自测口径，见
``scripts/gates/check_ast_parse_guards.py``）。``ast.parse`` 还会抛 ``ValueError`` 族
——实测 Python 3.14.6 对**孤立代理位**文本抛 ``UnicodeEncodeError``（null 字节抛的
是 ``SyntaxError`` 本体，不算新腿）——单腿守卫让这条腿从"读不懂 ⇒ 降级"分支里
**抛穿到调用方**；而已经降级的分支又把"读不懂"折叠进带判定含义的空结果
（``[]`` / ``set()`` / 原码 / ``ok=True``），读数侧分不清"干净"与"没读出来"。

修复口径（判定不变，只补披露）：
    1. 捕获面收敛为 ``check_status.AST_UNREADABLE_ERRORS = (SyntaxError, ValueError)``；
    2. "读不懂"的形态归因收敛为 ``unparseable_shape()``（fenced_block / git_diff /
       undecodable / syntax），错误文案收敛为 ``parse_error_text()``；
    3. 四个模块（deterministic_repair / cross_file / expert_pool / patch_intent）经
       ``outcome_sink`` 侧信道披露，三个发布点（graph/debugger 两条分支 +
       agents/debugger 编辑意图）把 ``check_status`` / ``check_outcomes`` 写入观测键；
    4. 棘轮门禁阻断"新写一个单腿守卫"，豁免按 (站点数, 折叠形态) 计额度。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.graph.expert_pool import ExpertPoolAgent, _normalize_patch_for_voting
from src.tools.cross_file import _collect_reverse_deps, analyze_cross_file_deps
from src.tools.deterministic_repair import _insert_import, _top_level_names, attempt_deterministic_repair
from src.tools.oracle_validator import _unparseable_test_reason
from src.tools.patch_intent import apply_edit_intents
from src.utils.check_status import (
    AST_UNREADABLE_ERRORS,
    CHECK_DISABLED,
    CHECK_ERROR,
    CHECK_OK,
    CHECK_STATUS_VOCABULARY,
    UNPARSEABLE_FENCED,
    UNPARSEABLE_GIT_DIFF,
    UNPARSEABLE_SYNTAX,
    UNPARSEABLE_UNDECODABLE,
    parse_error_text,
    parses_as_module,
    unparseable_shape,
    worst_check_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

VALID = "def f():\n    return 1\n"
SYNTAX = "def f(:\n"
FENCED = "```python\ndef f():\n    return 1\n```"
#: 带统一差异头的文本：压根不该进 AST 门（BK 轮补入 git_diff 形态）。
GIT_DIFF = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-def f():\n+def f():\n"
#: 只有 hunk 头、没有 ``diff --git`` 行的差异片段（同样不是"坏了的 Python"）。
GIT_HUNK_ONLY = "@@ -1,3 +1,4 @@\n def f():\n-    return 1\n+    return 2\n"
#: 孤立代理位：``ast.parse`` 在此抛 ``UnicodeEncodeError``（ValueError 子类）。
SURROGATE = "x = '\ud800'\n"
#: null 字节：3.14.6 抛的是 ``SyntaxError`` 本体（对账归 syntax，不是新腿）。
NUL_BYTE = "x = 1\x00\n"
EMPTY = "   \n"


def _leg(sink: list[dict[str, Any]], check: str) -> dict[str, Any]:
    """取某条腿的记录（测试输入保证同名只有一条）。"""
    hits = [item for item in sink if item["check"] == check]
    assert hits, f"sink 缺 {check} 腿：{sink}"
    return hits[0]


def _load_capture_ratchet() -> Any:
    """以 importlib 加载 scripts/gates/check_ast_parse_guards.py（scripts 非包）。"""
    spec = importlib.util.spec_from_file_location(
        "check_ast_parse_guards_under_test",
        PROJECT_ROOT / "scripts" / "gates" / "check_ast_parse_guards.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(PROJECT_ROOT))
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_capture_ratchet()


class TestCaptureSurface:
    """捕获面本体：ValueError 族必须在常量里，且 ``parses_as_module`` 不抛穿。"""

    def test_vocabulary_is_syntax_and_value_error(self) -> None:
        capture_surface = AST_UNREADABLE_ERRORS
        assert capture_surface == (SyntaxError, ValueError)

    def test_raw_ast_parse_escapes_a_single_leg_guard(self) -> None:
        """抛穿面的存在性证据：``except SyntaxError`` 拦不住孤立代理位。"""
        with pytest.raises(UnicodeEncodeError):
            ast.parse(SURROGATE)

    def test_parses_as_module_returns_false_instead_of_escaping(self) -> None:
        assert parses_as_module(SURROGATE) is False
        assert parses_as_module(NUL_BYTE) is False
        assert parses_as_module(GIT_DIFF) is False
        assert parses_as_module(SYNTAX) is False
        assert parses_as_module(VALID) is True

    def test_shared_constant_actually_catches_the_escape_leg(self) -> None:
        """常量必须真的接住抛穿那条腿（否则只是装饰）。"""
        try:
            ast.parse(SURROGATE)
        except AST_UNREADABLE_ERRORS:
            return
        pytest.fail("孤立代理位未被 AST_UNREADABLE_ERRORS 接住")


class TestUnparseableShape:
    """形态归因：读不懂 ≠ 语法错，四类成因必须可分。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (FENCED, UNPARSEABLE_FENCED),
            (GIT_DIFF, UNPARSEABLE_GIT_DIFF),
            (GIT_HUNK_ONLY, UNPARSEABLE_GIT_DIFF),
            (SURROGATE, UNPARSEABLE_UNDECODABLE),
            (SYNTAX, UNPARSEABLE_SYNTAX),
            (NUL_BYTE, UNPARSEABLE_SYNTAX),
        ],
    )
    def test_shape_labels(self, text: str, expected: str) -> None:
        assert unparseable_shape(text) == expected

    def test_parse_error_text_prefers_syntaxerror_msg_and_falls_back_to_str(self) -> None:
        try:
            ast.parse(SYNTAX)
        except SyntaxError as exc:
            assert parse_error_text(exc) == exc.msg
        try:
            ast.parse(SURROGATE)
        except UnicodeEncodeError as exc:
            assert parse_error_text(exc) == str(exc)


class TestDeterministicRepairDisclosure:
    """确定性修复入口：目标读不懂 / 候选未过门各自的披露与判定不变式。"""

    def test_unreadable_target_discloses_shape(self) -> None:
        sink: list[dict[str, Any]] = []
        out = attempt_deterministic_repair(target_code=SURROGATE, test_output="", outcome_sink=sink)
        assert _leg(sink, "target_readability") == {
            "check": "target_readability",
            "status": CHECK_ERROR,
            "reason": f"unparseable_target:{UNPARSEABLE_UNDECODABLE}",
        }
        assert out["patch_code"] is None
        assert out["category"] == ""

    def test_readable_target_records_ok_leg(self) -> None:
        sink: list[dict[str, Any]] = []
        attempt_deterministic_repair(target_code=VALID, test_output="", outcome_sink=sink)
        assert _leg(sink, "target_readability") == {
            "check": "target_readability",
            "status": CHECK_OK,
            "reason": "target_parsed",
        }

    def test_empty_target_is_error_not_disabled(self) -> None:
        """空目标沿用旧 reason（判定值不变），但可读性腿必须是 error 而非静默。"""
        sink: list[dict[str, Any]] = []
        out = attempt_deterministic_repair(target_code=EMPTY, test_output="", outcome_sink=sink)
        assert out["reason"] == "empty_target"
        assert sink == [{"check": "target_readability", "status": CHECK_ERROR, "reason": "empty_target"}]

    def test_judgment_identical_with_and_without_sink(self) -> None:
        """侧信道不得改变判定值：同输入下返回体逐键相等。"""
        for text in (VALID, SYNTAX, FENCED, GIT_DIFF, SURROGATE, NUL_BYTE, EMPTY):
            plain = attempt_deterministic_repair(target_code=text, test_output="import json\n")
            with_sink = attempt_deterministic_repair(target_code=text, test_output="import json\n", outcome_sink=[])
            assert plain == with_sink, text

    def test_top_level_names_survives_unreadable(self) -> None:
        assert _top_level_names(SURROGATE) == set()
        assert _top_level_names(VALID) == {"f"}

    def test_insert_import_survives_unreadable(self) -> None:
        assert _insert_import(SURROGATE, "json").startswith("import json\n")
        assert _insert_import(VALID, "json").startswith("import json\n")


class TestCrossFileDisclosure:
    """跨文件依赖：空列表的两种成因（没有边 / 没读出来）必须可分。"""

    def test_unreadable_entry_returns_empty_and_discloses(self) -> None:
        sink: list[dict[str, Any]] = []
        deps = analyze_cross_file_deps("entry", {"entry": SURROGATE}, outcome_sink=sink)
        assert deps == []
        assert sink == [
            {
                "check": "entry_readability",
                "status": CHECK_ERROR,
                "reason": f"unparseable_entry:{UNPARSEABLE_UNDECODABLE}",
            }
        ]

    def test_missing_entry_is_disabled_not_error(self) -> None:
        sink: list[dict[str, Any]] = []
        assert analyze_cross_file_deps("entry", {"other": VALID}, outcome_sink=sink) == []
        assert sink == [{"check": "entry_readability", "status": CHECK_DISABLED, "reason": "entry_not_in_source_files"}]

    def test_reverse_scan_discloses_per_unreadable_module_then_scan_count(self) -> None:
        sink: list[dict[str, Any]] = []
        files = {"entry": VALID, "bad_one": SURROGATE, "bad_two": SYNTAX, "good": "import entry\n"}
        _collect_reverse_deps("entry", files, outcome_sink=sink)
        assert sink == [
            {
                "check": "reverse_dep_scan",
                "status": CHECK_ERROR,
                "reason": f"unparseable_module:bad_one:{UNPARSEABLE_UNDECODABLE}",
            },
            {
                "check": "reverse_dep_scan",
                "status": CHECK_ERROR,
                "reason": f"unparseable_module:bad_two:{UNPARSEABLE_SYNTAX}",
            },
            {"check": "reverse_dep_scan", "status": CHECK_OK, "reason": "modules_scanned:1"},
        ]
        assert worst_check_status(str(item["status"]) for item in sink) == CHECK_ERROR

    def test_reverse_scan_without_any_module_is_disabled(self) -> None:
        sink: list[dict[str, Any]] = []
        _collect_reverse_deps("entry", {"entry": VALID}, outcome_sink=sink)
        assert sink == [{"check": "reverse_dep_scan", "status": CHECK_DISABLED, "reason": "no_module_scanned"}]

    def test_judgment_identical_with_and_without_sink(self) -> None:
        grids = [
            ("entry", {"entry": SURROGATE}),
            ("entry", {"entry": GIT_DIFF}),
            ("entry", {"entry": "import helper\n", "helper": SURROGATE}),
            ("entry", {"entry": VALID, "helper": VALID}),
        ]
        for entry, files in grids:
            plain = analyze_cross_file_deps(entry, files, bidirectional=True)
            with_sink = analyze_cross_file_deps(entry, files, bidirectional=True, outcome_sink=[])
            assert plain == with_sink, files


class TestExpertPoolDisclosure:
    """投票归一化：走"原文参与投票"保守支时，候选到底被读过没有必须可读。"""

    def test_unreadable_patch_returns_original_and_discloses(self) -> None:
        sink: list[dict[str, Any]] = []
        assert _normalize_patch_for_voting(SURROGATE, outcome_sink=sink) == SURROGATE
        assert sink == [
            {
                "check": "patch_normalization",
                "status": CHECK_ERROR,
                "reason": f"unparseable_patch:{UNPARSEABLE_UNDECODABLE}",
            }
        ]

    def test_empty_patch_is_disabled(self) -> None:
        sink: list[dict[str, Any]] = []
        assert _normalize_patch_for_voting("", outcome_sink=sink) == ""
        assert sink == [{"check": "patch_normalization", "status": CHECK_DISABLED, "reason": "empty_patch"}]

    def test_normalized_patch_records_ok(self) -> None:
        sink: list[dict[str, Any]] = []
        _normalize_patch_for_voting(VALID, outcome_sink=sink)
        assert sink == [{"check": "patch_normalization", "status": CHECK_OK, "reason": "normalized"}]

    def test_cross_validate_prefixes_reason_with_dimension(self) -> None:
        sink: list[dict[str, Any]] = []
        pool = ExpertPoolAgent()
        candidates = [
            {"dimension": "logic", "patch": SURROGATE, "expert_failed": False},
            {"dimension": "edge", "patch": VALID, "expert_failed": False},
            {"dimension": "style", "patch": "", "expert_failed": True},
        ]
        verified = pool.cross_validate(candidates, min_agreement=1, outcome_sink=sink)
        assert [item["reason"] for item in sink] == [
            f"logic:unparseable_patch:{UNPARSEABLE_UNDECODABLE}",
            "edge:normalized",
        ]
        assert all(item["status"] in CHECK_STATUS_VOCABULARY for item in sink)
        assert len(verified) == 2

    def test_cross_validate_judgment_identical_with_and_without_sink(self) -> None:
        pool = ExpertPoolAgent()
        candidates = [
            {"dimension": "logic", "patch": SURROGATE, "expert_failed": False},
            {"dimension": "edge", "patch": FENCED, "expert_failed": False},
        ]
        plain = pool.cross_validate([dict(c) for c in candidates], min_agreement=1)
        with_sink = pool.cross_validate([dict(c) for c in candidates], min_agreement=1, outcome_sink=[])
        assert plain == with_sink


class TestPatchIntentDisclosure:
    """编辑意图落盘：``ok=True`` 的两种成因必须可分，五个判定字段取值不变。"""

    def test_unreadable_original_but_readable_result_discloses_both(self) -> None:
        sink: list[dict[str, Any]] = []
        out = apply_edit_intents(SURROGATE, [{"old_str": "x = '\ud800'", "new_str": "x = 1"}], outcome_sink=sink)
        assert out["ok"] is True
        assert out["code"] == "x = 1\n"
        assert _leg(sink, "original_readability") == {
            "check": "original_readability",
            "status": CHECK_ERROR,
            "reason": f"unparseable_original:{UNPARSEABLE_UNDECODABLE}",
        }
        assert _leg(sink, "edit_result_readability") == {
            "check": "edit_result_readability",
            "status": CHECK_OK,
            "reason": "result_parsed",
        }

    def test_preexisting_unreadable_still_ok_but_discloses_error(self) -> None:
        sink: list[dict[str, Any]] = []
        out = apply_edit_intents(SYNTAX, [{"old_str": "def f(:", "new_str": "def g(:"}], outcome_sink=sink)
        assert out["ok"] is True
        assert any(d.startswith("result_syntax_error_preexisting:") for d in out["diagnostics"])
        leg = _leg(sink, "edit_result_readability")
        assert leg["status"] == CHECK_ERROR
        assert leg["reason"].startswith("preexisting_unreadable:")

    def test_edit_regression_is_error_and_rolls_back(self) -> None:
        sink: list[dict[str, Any]] = []
        out = apply_edit_intents(VALID, [{"old_str": "return 1", "new_str": "return ("}], outcome_sink=sink)
        assert out["ok"] is False
        assert out["code"] == VALID
        leg = _leg(sink, "edit_result_readability")
        assert leg["status"] == CHECK_ERROR
        assert leg["reason"].startswith("unparseable_result:")

    def test_empty_original_is_disabled(self) -> None:
        sink: list[dict[str, Any]] = []
        out = apply_edit_intents(EMPTY, [{"old_str": "a", "new_str": "b"}], outcome_sink=sink)
        assert out["ok"] is False
        assert sink == [{"check": "original_readability", "status": CHECK_DISABLED, "reason": "empty_original_code"}]

    def test_judgment_fields_identical_with_and_without_sink(self) -> None:
        cases = [
            (SURROGATE, [{"old_str": "x = '", "new_str": "x = 1"}]),
            (SYNTAX, [{"old_str": "def f(:", "new_str": "def g(:"}]),
            (FENCED, [{"old_str": "return 1", "new_str": "return 2"}]),
            (GIT_DIFF, [{"old_str": "-def f():", "new_str": "+def f():"}]),
            (VALID, [{"old_str": "return 1", "new_str": "return ("}]),
            (VALID, [{"old_str": "return 1", "new_str": "return 2"}]),
        ]
        for code, intents in cases:
            plain = apply_edit_intents(code, intents)
            with_sink = apply_edit_intents(code, intents, outcome_sink=[])
            assert plain == with_sink, (code, intents)


class TestMultiCandidateDisclosure:
    """多候选/合成层：BK 的回归锁在这里**当场抓到过抛穿**（节点整体崩）。

    修复前的现场：``_func_signatures`` 只捕 ``SyntaxError``，孤立代理位候选的
    ``UnicodeEncodeError`` 从 ``_debugger_node`` 里穿出，整个修复节点崩掉——
    这不是"折叠成静默"的存量站点，而是会炸调用方的站点，故本轮连捕获面一起收。
    """

    def test_static_validate_patch_keeps_syntax_error_reason_unchanged(self) -> None:
        import src.tools.multi_candidate as mc

        ok, reason, applied = mc.static_validate_patch(VALID, "```python\ndef f(:\n```")
        assert ok is False and applied == ""
        assert reason.startswith("语法错误（line ")

    def test_static_validate_patch_folds_undecodable_instead_of_escaping(self) -> None:
        import src.tools.multi_candidate as mc

        original = "def f():\n    return 1\n"
        patch = "```python\ndef f():\n    return '\ud800'\n```"
        sink: list[dict[str, Any]] = []
        ok, reason, applied = mc.static_validate_patch(original, patch, outcome_sink=sink)
        assert (ok, applied) == (False, "")
        assert reason.startswith(f"代码读不懂（{UNPARSEABLE_UNDECODABLE}）")
        assert sink == [
            {"check": "patch_validation", "status": CHECK_ERROR, "reason": f"unreadable:{UNPARSEABLE_UNDECODABLE}"}
        ]

    def test_static_validate_patch_records_ok_leg(self) -> None:
        import src.tools.multi_candidate as mc

        sink: list[dict[str, Any]] = []
        ok, _, _ = mc.static_validate_patch(
            "def f():\n    return 1\n", "```python\ndef f():\n    return 2\n```", outcome_sink=sink
        )
        assert ok is True
        assert sink == [{"check": "patch_validation", "status": CHECK_OK, "reason": "patch_parsed"}]

    def test_region_scan_over_reports_when_candidate_is_unreadable(self) -> None:
        """实测口径（不是推测）：候选读不懂 ⇒ ``new_sigs`` 为空 ⇒ 原代码全部顶层名
        被判为"已修改"。方向是保守的（宁可多报重叠也不漏判可合成），但代价是
        ``region_labels`` 里会出现从未真读出来的区域名——这正是必须披露
        ``unparseable_candidate`` 的原因。
        """
        import src.tools.multi_candidate as mc

        sink: list[dict[str, Any]] = []
        assert mc._extract_modified_regions(VALID, SURROGATE, outcome_sink=sink) == {"f"}
        assert sink == [
            {
                "check": "synthesis_input_readability",
                "status": CHECK_ERROR,
                "reason": f"unparseable_candidate:{UNPARSEABLE_UNDECODABLE}",
            }
        ]
        assert mc._extract_modified_regions(VALID, SURROGATE) == {"f"}

    def test_single_unreadable_candidate_fails_closed_instead_of_crashing(self) -> None:
        """BK 锁实测抓到的真缺陷：单候选读不懂时流程走到结果门，旧口径的
        ``except SyntaxError`` 拦不住孤立代理位 ⇒ ``UnicodeEncodeError`` 抛穿
        ``_debugger_node``。收口后判定值仍是空串（回退单候选），只多披露。
        """
        import src.tools.multi_candidate as mc

        candidates = [mc.CandidateResult(index=0, patch="p0", new_code=SURROGATE, static_passed=True)]
        sink: list[dict[str, Any]] = []
        code, labels = mc.synthesize_candidates(VALID, candidates, outcome_sink=sink)
        assert code == ""
        assert labels == ["f"]
        assert [item["check"] for item in sink] == ["synthesis_input_readability", "synthesis_result_readability"]
        assert [item["status"] for item in sink] == [CHECK_ERROR, CHECK_ERROR]
        detail = str(sink[1]["reason"])
        assert detail.startswith("unparseable_result:")
        # 错误文案必须可安全落盘：Python 的编解码错误消息里是 \ud800 的字面转义，
        # 而不是孤立代理位本体（否则观测键自身会二次抛穿）。
        assert detail.encode("utf-8")
        assert worst_check_status(str(item["status"]) for item in sink) == CHECK_ERROR

    def test_two_unreadable_candidates_degenerate_to_overlap_refusal(self) -> None:
        """两候选都读不懂 ⇒ 区域集合必然重叠 ⇒ 在输入侧就拒绝，不走到结果门。"""
        import src.tools.multi_candidate as mc

        candidates = [
            mc.CandidateResult(index=0, patch="p0", new_code=SURROGATE, static_passed=True),
            mc.CandidateResult(index=1, patch="p1", new_code=SURROGATE, static_passed=True),
        ]
        sink: list[dict[str, Any]] = []
        code, labels = mc.synthesize_candidates(VALID, candidates, outcome_sink=sink)
        assert code == ""
        assert labels == ["f", "f"]
        assert [item["reason"] for item in sink] == [
            f"unparseable_candidate:{UNPARSEABLE_UNDECODABLE}",
            f"unparseable_candidate:{UNPARSEABLE_UNDECODABLE}",
        ]

    def test_unreadable_merge_source_is_dropped_while_result_claims_ok(self) -> None:
        """折叠形态锁：读不懂的候选被跳过后返回值仍是"合成成功"——
        ``code`` 恰等于另一个候选的全文，判定侧看不出少并了一个候选。收口口径是
        不动返回值、在侧信道记 ``unparseable_merge_source``，且发布点按最坏腿聚合
        （只看 ``synthesis_result_readability`` 会读到假的 ok）。
        """
        import src.tools.multi_candidate as mc

        readable = VALID + "\n\ndef g():\n    return 2\n"
        candidates = [
            mc.CandidateResult(index=0, patch="p0", new_code=readable, static_passed=True),
            mc.CandidateResult(index=1, patch="p1", new_code=SURROGATE, static_passed=True),
        ]
        sink: list[dict[str, Any]] = []
        code, labels = mc.synthesize_candidates(VALID, candidates, outcome_sink=sink)
        assert code == readable
        assert labels == ["g", "f"]
        assert [item["reason"] for item in sink] == [
            f"unparseable_candidate:{UNPARSEABLE_UNDECODABLE}",
            f"unparseable_merge_source:{UNPARSEABLE_UNDECODABLE}",
            "synthesized",
        ]
        assert [item["status"] for item in sink] == [CHECK_ERROR, CHECK_ERROR, CHECK_OK]
        assert worst_check_status(str(item["status"]) for item in sink) == CHECK_ERROR

    def test_synthesize_records_ok_leg_on_success(self) -> None:
        import src.tools.multi_candidate as mc

        original = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
        cand_a = "def a():\n    return 9\n\n\ndef b():\n    return 2\n"
        cand_b = "def a():\n    return 1\n\n\ndef b():\n    return 8\n"
        candidates = [
            mc.CandidateResult(index=0, patch="p0", new_code=cand_a, static_passed=True),
            mc.CandidateResult(index=1, patch="p1", new_code=cand_b, static_passed=True),
        ]
        sink: list[dict[str, Any]] = []
        code, _ = mc.synthesize_candidates(original, candidates, outcome_sink=sink)
        assert code
        assert {"check": "synthesis_result_readability", "status": CHECK_OK, "reason": "synthesized"} in sink
        assert worst_check_status(str(item["status"]) for item in sink) == CHECK_OK

    def test_judgment_identical_with_and_without_sink(self) -> None:
        import src.tools.multi_candidate as mc

        grids = [
            (VALID, [mc.CandidateResult(index=0, patch="p", new_code=SURROGATE, static_passed=True)]),
            (SURROGATE, [mc.CandidateResult(index=0, patch="p", new_code=VALID, static_passed=True)]),
            (SYNTAX, [mc.CandidateResult(index=0, patch="p", new_code="def f(:\n", static_passed=True)]),
        ]
        for original, candidates in grids:
            plain = mc.synthesize_candidates(original, list(candidates))
            with_sink = mc.synthesize_candidates(original, list(candidates), outcome_sink=[])
            assert plain == with_sink, original


class TestBjBkReasonCaliber:
    """BJ（oracle 层）与 BK（共享形态词表）的归因口径对账锁。

    BJ 轮手册 §3 的读数依赖 ``unparseable_test:fenced_block`` / ``:syntax`` 两个字面量，
    故本轮未改 ``oracle_validator``；本锁钉住"两者对围栏/语法一致、对 git_diff 与
    不可编码暂不一致"的现状——下游若要合并口径必须同时更正 BJ 的登记读数。
    """

    def test_fenced_and_syntax_labels_agree_with_bj(self) -> None:
        for text in (FENCED, SYNTAX, "def f(:\n    return 1\n```"):
            assert _unparseable_test_reason(text) == f"unparseable_test:{unparseable_shape(text)}"

    def test_diff_and_undecodable_divergence_is_registered_not_silent(self) -> None:
        assert _unparseable_test_reason(GIT_DIFF) == "unparseable_test:syntax"
        assert unparseable_shape(GIT_DIFF) == UNPARSEABLE_GIT_DIFF
        assert _unparseable_test_reason(SURROGATE) == "unparseable_test:syntax"
        assert unparseable_shape(SURROGATE) == UNPARSEABLE_UNDECODABLE


def _run_node(state: dict[str, Any], agent: MagicMock, **values: object) -> dict[str, Any]:
    """在统一 mock 骨架下运行 ``_debugger_node``（同 test_debugger_node_branches 口径）。"""
    from src.graph.debugger import _debugger_node

    with ExitStack() as stack:
        stack.enter_context(patch("src.graph.debugger._get_or_create_debugger_agent", return_value=agent))
        stack.enter_context(patch("src.agents.fault_localizer.fault_localizer_enabled", return_value=False))
        for target, value in values.items():
            stack.enter_context(patch(target, return_value=value))
        return _debugger_node(state)


def _node_agent() -> MagicMock:
    agent = MagicMock()
    agent.debug.return_value = {
        "root_cause": "r",
        "error_category": "logic_error",
        "fix_strategy": "s",
        "patch": "def foo():\n    return 1\n",
    }
    return agent


def _base_state(**overrides: object) -> dict[str, Any]:
    state: dict[str, Any] = {
        "target_code": VALID,
        "target_file": "foo.py",
        "module_name": "foo",
        "test_output": "AssertionError: assert 4 == 0",
        "generated_test": "def test_foo():\n    assert foo() == 1\n",
        "failed_cases": [],
        "iteration": 0,
        "error_category": "logic_error",
        "task_uuid": "task-bk",
        "repair_history": [],
        "deterministic_repair_status": None,
    }
    state.update(overrides)
    return state


class TestPublisherLegs:
    """三个发布点：侧信道必须真的落到观测键上，聚合取最差者，且不与既有键撞名。"""

    def test_deterministic_branch_publishes_error_status(self) -> None:
        result = _run_node(
            _base_state(target_code=SURROGATE),
            _node_agent(),
            **{"src.graph.debugger.deterministic_repair_first_enabled": True},
        )
        status = result["deterministic_repair_status"]
        assert set(status) == {"attempted", "method", "reason", "patch_produced", "check_status", "check_outcomes"}
        assert status["check_status"] == CHECK_ERROR
        assert [item["reason"] for item in status["check_outcomes"]] == [
            f"unparseable_target:{UNPARSEABLE_UNDECODABLE}"
        ]

    def test_deterministic_branch_keeps_legacy_keys_when_target_readable(self) -> None:
        """新增键只做加法：原有四键的取值口径不受影响（判定不变）。"""
        result = _run_node(
            _base_state(target_code="def foo():\n    return 1\n"),
            _node_agent(),
            **{"src.graph.debugger.deterministic_repair_first_enabled": True},
        )
        status = result["deterministic_repair_status"]
        assert status["check_status"] == CHECK_OK
        assert {"attempted", "method", "reason", "patch_produced"} <= set(status)

    def test_empty_sink_aggregates_to_error_default(self) -> None:
        """没读出任何腿（例如池被 mock 掉）⇒ 默认 error，不给"干净"的假象。"""
        assert worst_check_status([]) == CHECK_ERROR

    def test_expert_pool_branch_publishes_per_candidate_legs(self) -> None:
        real = ExpertPoolAgent()
        pool = MagicMock()
        pool.generate_parallel.return_value = [
            {"dimension": "logic", "patch": SURROGATE, "new_code": SURROGATE, "expert_failed": False},
            {"dimension": "edge", "patch": SURROGATE, "new_code": SURROGATE, "expert_failed": False},
        ]
        pool.cross_validate.side_effect = lambda candidates, min_agreement=2, outcome_sink=None: (
            ExpertPoolAgent.cross_validate(real, candidates, min_agreement=min_agreement, outcome_sink=outcome_sink)
        )
        result = _run_node(
            _base_state(task_uuid="task-bk-ep"),
            _node_agent(),
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": pool,
                "src.tools.strategy_bank.strategy_bank_enabled": False,
            },
        )
        meta = result["expert_pool_meta"]
        assert meta["check_status"] == CHECK_ERROR
        checks = {item["check"] for item in meta["check_outcomes"]}
        # 同一个 sink 同时接投票层与合成层（BK 轮把 worst_check_status 改为在写入时
        # 内联计算，正是为了让合成腿也参与聚合）。本场景两个候选都读不懂 ⇒ 区域退化
        # 为重叠、在输入侧就被拒绝，因此没有结果腿（结果腿由单元锁单独锁）。
        assert checks == {"patch_normalization", "synthesis_input_readability"}
        assert any(item["reason"].startswith("logic:") for item in meta["check_outcomes"])
        assert any(item["reason"].startswith("edge:") for item in meta["check_outcomes"])
        assert any(
            item["reason"] == f"unparseable_candidate:{UNPARSEABLE_UNDECODABLE}" for item in meta["check_outcomes"]
        )

    def test_edit_intent_publisher_writes_both_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents.debugger import DebuggerAgent

        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        response = (
            '{"root_cause": "r", "error_category": "ASSERTION", "fix_strategy": "s", '
            '"patch": "```python\\nWHOLE FILE\\n```", '
            '"edit_intents": [{"old_str": "x = \'\\ud800\'", "new_str": "x = 1"}]}'
        )
        agent = DebuggerAgent()
        with patch.object(agent, "_call_llm", return_value=response):
            result = agent.debug(
                target_code=SURROGATE,
                test_output="UnicodeEncodeError: surrogates not allowed",
                failed_cases=[{"name": "test_x", "error": "surrogates"}],
            )
        status = result["edit_intent_status"]
        assert status["ok"] is True
        assert status["check_status"] == CHECK_ERROR
        reasons = [item["reason"] for item in status["check_outcomes"]]
        assert f"unparseable_original:{UNPARSEABLE_UNDECODABLE}" in reasons


class TestCaptureRatchetGate:
    """棘轮本体：违规判定、豁免额度与正向对照（缺一即空转）。"""

    def test_src_current_state_is_green_at_registered_denominators(self, gate: Any) -> None:
        paths = gate._iter_py_dirs([gate.SRC_DIR])
        violations, sites, hits = gate.scan(paths)
        assert violations == []
        # BK 收口读数（含 try 句子树内的解析调用）。
        # BR（2026-10-22）：+1 = `executor_imports._insert_sys_path_prefix`——
        # F04 的 docstring/future 让位插入需要 AST 定界；该站点直接捕获共享
        # `AST_UNREADABLE_ERRORS`，不新增豁免（EXEMPT 与命中数不变）。
        assert sites == 79
        assert len(hits) == sum(quota for quota, _ in gate.EXEMPT.values()) == 20
        assert set(gate.EXEMPT) == set(hits)

    def test_exempt_quotas_are_consistent_with_the_vocabulary(self, gate: Any) -> None:
        """豁免值必须是 (站点数≥1, 非空折叠形态)。"""
        for key, (quota, fold) in gate.EXEMPT.items():
            assert "::" in key and quota >= 1 and fold, key

    def test_positive_control_new_single_leg_guard_is_caught(self, gate: Any, tmp_path: Path) -> None:
        """正向对照：新写的单腿守卫必须违规（否则棘轮证明不了任何事）。"""
        module = tmp_path / "newsite.py"
        module.write_text(
            "import ast\n\n\ndef f(code):\n    try:\n        ast.parse(code)\n    except SyntaxError:\n        return []\n",
            encoding="utf-8",
        )
        violations, sites, hits = gate.scan([module], root=tmp_path)
        assert sites == 1
        assert hits == []
        assert len(violations) == 1
        assert "未登记豁免" in violations[0][1]

    def test_positive_control_shared_capture_surface_passes(self, gate: Any, tmp_path: Path) -> None:
        """改用共享捕获面后同一站点必须放行（口径真的被执行，而不是形同虚设）。"""
        module = tmp_path / "goodsite.py"
        module.write_text(
            "import ast\n\n\ndef f(code):\n"
            "    try:\n        ast.parse(code)\n"
            "    except (SyntaxError, ValueError):\n        return []\n",
            encoding="utf-8",
        )
        violations, sites, _ = gate.scan([module], root=tmp_path)
        assert sites == 1
        assert violations == []

    def test_positive_control_valueerror_subclass_only_is_caught(self, gate: Any, tmp_path: Path) -> None:
        """只接住 ``UnicodeEncodeError``（ValueError 的子类）不算合格：族内成员不止一个。"""
        module = tmp_path / "partial.py"
        module.write_text(
            "import ast\n\n\ndef f(code):\n    try:\n        ast.parse(code)\n"
            "    except (SyntaxError, UnicodeEncodeError):\n        return []\n",
            encoding="utf-8",
        )
        violations, _, _ = gate.scan([module], root=tmp_path)
        assert len(violations) == 1

    def test_over_quota_site_inside_exempted_function_is_caught(self, gate: Any, tmp_path: Path) -> None:
        """额度按站点计：在已豁免的函数里再加一处单腿守卫同样违规。"""
        pkg = tmp_path / "agents"
        pkg.mkdir()
        module = pkg / "deterministic_guard.py"
        module.write_text(
            "import ast\n\n\ndef scan_test_file(code):\n"
            "    try:\n        ast.parse(code)\n    except SyntaxError:\n        pass\n"
            "    try:\n        ast.parse(code)\n    except SyntaxError:\n        pass\n",
            encoding="utf-8",
        )
        violations, sites, hits = gate.scan([module], root=tmp_path)
        assert sites == 2
        assert len(hits) == 1
        assert len(violations) == 1
        assert "超出豁免额度 1 处" in violations[0][1]

    def test_gate_covers_every_exempt_key_with_a_real_site(self, gate: Any) -> None:
        """棘轮收紧的另一半：EXEMPT 里任何条目失配（站点已收敛）都该被 main 判失效。"""
        paths = gate._iter_py_dirs([gate.SRC_DIR])
        _, _, hits = gate.scan(paths)
        stale = sorted(set(gate.EXEMPT) - set(hits))
        assert stale == []
