"""patch_evidence 证据门单元测试（补齐 74% → 100%，2026-10-08）。

patch_evidence.py 此前无独立测试文件（仅被 _patch_applier_node 集成间接覆盖，
74%），本文件补齐证据判定全链路：gold / sbfl / keyword / none 四等级 +
diff 行号提取 + AST 行号 + 异常保守降级（零 LLM / 零网络 / 零子进程）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.tools.patch_evidence import (
    _ast_line_numbers,
    _keywords_hit,
    _patch_changed_lines,
    assess_patch_evidence,
    evidence_allows_write,
    patch_evidence_gate_enabled,
)

# ═══ 1. 证据门开关（PATCH_EVIDENCE_GATE_ENABLE）═══════════════════════════════


class TestGateSwitch:
    def test_default_true(self, monkeypatch):
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_ENABLE", raising=False)
        assert patch_evidence_gate_enabled() is True

    def test_false_when_disabled(self, monkeypatch):
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        assert patch_evidence_gate_enabled() is False


# ═══ 2. 关键词命中（_keywords_hit）════════════════════════════════════════════


class TestKeywordsHit:
    def test_empty_diagnosis_false(self):
        assert _keywords_hit("") is False

    def test_hit(self):
        assert _keywords_hit("测试用例断言写错") is True

    def test_miss(self):
        assert _keywords_hit("数组越界索引异常") is False


# ═══ 3. diff 行号提取（_patch_changed_lines）══════════════════════════════════


class TestPatchChangedLines:
    def test_empty_new_code_returns_empty(self):
        assert _patch_changed_lines("def f():\n    pass\n", "") == set()

    def test_same_code_returns_empty(self):
        code = "def f():\n    pass\n"
        assert _patch_changed_lines(code, code) == set()

    def test_changed_line_detected(self):
        original = "def f():\n    return 1\n"
        new = "def f():\n    return 2\n"
        assert 2 in _patch_changed_lines(original, new)

    def test_malformed_hunk_header_falls_back_to_zero(self):
        # 畸形 @@ 头（无 "+" 段）→ IndexError 捕获 → new_line 回退 0
        with patch("src.tools.patch_evidence.difflib.unified_diff", return_value=["@@ bad", "+x"]):
            changed = _patch_changed_lines("a", "b")
        assert changed == {1}  # +x 落在回退行号 1


# ═══ 4. AST 行号提取（_ast_line_numbers）══════════════════════════════════════


class TestAstLineNumbers:
    def test_empty_code(self):
        assert _ast_line_numbers("") == set()

    def test_normal_code(self):
        lines = _ast_line_numbers("def f():\n    return 1\n")
        assert 1 in lines

    def test_syntax_error_falls_back_to_all_lines(self):
        # SyntaxError → 保守退化为全行（不因解析失败漏掉可执行行）
        assert _ast_line_numbers("def f(:") == {1}


# ═══ 5. 证据等级判定（assess_patch_evidence）══════════════════════════════════


class TestAssessPatchEvidence:
    def test_gold_evidence_highest_priority(self):
        state = {"repo_verification": {"passed": True}}
        assert assess_patch_evidence(state, "a", "b") == "gold"

    def test_sbfl_evidence_overlap(self):
        state = {"fl_spectral_focus": {"top_k": [{"line": 2}]}}
        original = "def f():\n    return 1\n"
        new = "def f():\n    return 2\n"
        assert assess_patch_evidence(state, original, new) == "sbfl"

    def test_sbfl_no_overlap_falls_through(self):
        state = {"fl_spectral_focus": {"top_k": [{"line": 99}]}}
        original = "def f():\n    return 1\n"
        new = "def f():\n    return 2\n"
        assert assess_patch_evidence(state, original, new) == "none"

    def test_keyword_evidence(self):
        state = {"diagnosis": "测试用例断言写错"}
        assert assess_patch_evidence(state, "a", "b") == "keyword"

    def test_none_evidence(self):
        assert assess_patch_evidence({}, "a", "b") == "none"

    def test_all_exceptions_degrades_to_none(self):
        # 三个判定块逐一抛异常 → 全部 except pass → 保守 "none"（不误放行）
        state = MagicMock()
        state.get.side_effect = RuntimeError("boom")
        assert assess_patch_evidence(state, "a", "b") == "none"


# ═══ 6. 证据门放行判定（evidence_allows_write）════════════════════════════════


class TestEvidenceAllowsWrite:
    def test_gold_allows(self):
        assert evidence_allows_write("gold") is True

    def test_sbfl_allows(self):
        assert evidence_allows_write("sbfl") is True

    def test_keyword_denies(self):
        assert evidence_allows_write("keyword") is False

    def test_none_denies(self):
        assert evidence_allows_write("none") is False
