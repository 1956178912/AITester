"""agents/debugger 纯静态 / mock-LLM 分支补齐（2026-10-02 批次·八）。

锁定 debugger.py 的低覆盖纯逻辑分支（零真实 LLM / 零网络 / 零 subprocess）：
- _locate_repair_focus：行号解析 / 跨文件保护 / AST 解析失败 / 越界 / 无包围
  函数 / 最内层函数定位 / 列号注入 hint / focused 标志
- _locate_repair_focus_from_probe：探针快照空 / 首帧缺字段 / 跨文件 / 行号越界 /
  定位成功（probe_sourced=True）
- _build_position_aware_prompt_section：focused=False 返回空串 / focused=True 返回 hint
- _generate_adversarial_intents：LLM 输出 list / dict-with-hypotheses / 非 list+dict /
  异常 → 空列表（mock _call_llm_with_cache + extract_json_array + _extract_json）；
  T2（2026-10-11 独立评审落地）：补「顶层 JSON 数组必须被解析」回归锁——修复前该路径恒失败
- _build_adversarial_prompt_section：多假设注入 / 空假设
- _run_critic_eval：LLM 返回 break_cases + all_passed / 异常降级 all_passed=True
- _build_critic_feedback：break_cases 注入 / 空 break_cases
- _run_review_diagnosis：defect_type 合法 / 非法值保守归一 / 异常降级

所有 LLM 依赖方法经 mock _call_llm_with_cache + 解析层隔离，
零真实 LLM 调用（与本仓"纯静态 / 零 LLM"测试口径一致）。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _mk_ctx(line, filename=None, column=None, module_name=None) -> MagicMock:
    """构造 ErrorContext mock（debugger._locate_repair_focus 消费）。"""
    ctx = MagicMock()
    ctx.line = line
    ctx.filename = filename
    ctx.column = column
    ctx.module_name = module_name
    return ctx


def _mk_debugger() -> MagicMock:
    """构造 DebuggerAgent mock（实例化真实类，__init__ 零 LLM）。"""
    from src.agents.debugger import DebuggerAgent

    return DebuggerAgent()


# ─── _locate_repair_focus 分支 ───────────────────────────────────────────────


class TestLocateRepairFocusBranches:
    def test_invalid_line_returns_unfocused(self):
        dbg = _mk_debugger()
        for bad_line in (None, 0, -1, "5", 3.5):
            out = dbg._locate_repair_focus("def f():\n    return 1\n", _mk_ctx(bad_line), None)
            assert out["focused"] is False, f"line={bad_line!r} 应 focused=False"
            assert out["function_name"] is None

    def test_no_line_returns_unfocused(self):
        dbg = _mk_debugger()
        out = dbg._locate_repair_focus("def f():\n    return 1\n", _mk_ctx(None), None)
        assert out["focused"] is False
        assert out["hint"] == ""

    def test_cross_file_returns_unfocused(self):
        """traceback 文件名与 target_module 不符 → 不定位（避免误导修错文件）。"""
        dbg = _mk_debugger()
        ctx = _mk_ctx(2, filename="other_module.py")
        out = dbg._locate_repair_focus("def f():\n    return 1\n", ctx, "target_module")
        assert out["focused"] is False
        assert out["line"] == 2  # 行号保留，focused=False

    def test_cross_file_basename_match_locates(self):
        """basename == target_module（精确匹配）→ 定位成功。"""
        dbg = _mk_debugger()
        ctx = _mk_ctx(2, filename="mymodule.py")
        code = "def f():\n    x = 1\n    return x\n"
        out = dbg._locate_repair_focus(code, ctx, "mymodule")
        assert out["focused"] is True
        assert out["function_name"] == "f"

    def test_cross_file_py_suffix_match_locates(self):
        """basename == target_module + '.py'（后缀匹配）→ 定位成功。"""
        dbg = _mk_debugger()
        ctx = _mk_ctx(2, filename="mymodule.py")
        code = "def g():\n    return 2\n"
        out = dbg._locate_repair_focus(code, ctx, "mymodule")
        assert out["focused"] is True

    def test_syntax_error_returns_unfocused(self):
        """AST 解析失败（SYNTAX 类）→ 降级全文件重写。"""
        dbg = _mk_debugger()
        ctx = _mk_ctx(1)
        out = dbg._locate_repair_focus("def f(:\n", ctx, None)
        assert out["focused"] is False
        assert out["hint"] == ""

    def test_out_of_range_line_returns_unfocused(self):
        """行号越界（超出代码行数）→ 无包围函数。"""
        dbg = _mk_debugger()
        ctx = _mk_ctx(99)
        out = dbg._locate_repair_focus("def f():\n    return 1\n", ctx, None)
        assert out["focused"] is False

    def test_locates_innermost_function(self):
        """嵌套函数：取包围区间最短（最内层）的函数。"""
        dbg = _mk_debugger()
        code = "def outer():\n    def inner():\n        x = 1\n        return x\n    return inner()\n"
        # inner 体在 L4-5，异常定位到 L4
        ctx = _mk_ctx(4)
        out = dbg._locate_repair_focus(code, ctx, None)
        assert out["focused"] is True
        assert out["function_name"] == "inner"

    def test_async_function_located(self):
        """AsyncFunctionDef 也纳入包围区间。"""
        dbg = _mk_debugger()
        code = "async def a():\n    await _x()\n    return 1\n"
        ctx = _mk_ctx(2)
        out = dbg._locate_repair_focus(code, ctx, None)
        assert out["focused"] is True
        assert out["function_name"] == "a"

    def test_hint_includes_column_when_positive(self):
        dbg = _mk_debugger()
        code = "def f():\n    return 1\n"
        ctx = _mk_ctx(2, column=5)
        out = dbg._locate_repair_focus(code, ctx, None)
        assert "第 5 列" in out["hint"]
        assert out["focused"] is True

    def test_hint_omits_column_when_zero_or_missing(self):
        for col in (None, 0, -1, "x"):
            dbg = _mk_debugger()
            code = "def f():\n    return 1\n"
            ctx = _mk_ctx(2, column=col)
            out = dbg._locate_repair_focus(code, ctx, None)
            assert "列" not in out["hint"], f"col={col!r} 不应注入列号"


# ─── _locate_repair_focus_from_probe 分支 ────────────────────────────────────


class TestLocateRepairFocusFromProbeBranches:
    def test_empty_snapshot_returns_unfocused(self):
        dbg = _mk_debugger()
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", None, None)
        assert out["focused"] is False
        assert out["probe_sourced"] is True

    def test_empty_frames_returns_unfocused(self):
        dbg = _mk_debugger()
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", {"frames": []}, None)
        assert out["focused"] is False

    def test_first_frame_missing_line_returns_unfocused(self):
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "f"}]}  # 无 line
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", snap, None)
        assert out["focused"] is False

    def test_first_frame_invalid_line_returns_unfocused(self):
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "f", "line": 0}]}
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", snap, None)
        assert out["focused"] is False

    def test_cross_file_probe_returns_unfocused(self):
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "f", "file": "other.py", "line": 2}]}
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", snap, "target_mod")
        assert out["focused"] is False

    def test_out_of_range_probe_line_returns_unfocused(self):
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "f", "line": 99}]}
        out = dbg._locate_repair_focus_from_probe("def f():\n    return 1\n", snap, None)
        assert out["focused"] is False

    def test_successful_probe_locates_function(self):
        dbg = _mk_debugger()
        code = "def outer():\n    def inner():\n        return 1\n    return inner()\n"
        snap = {"frames": [{"function": "inner", "line": 3}]}
        out = dbg._locate_repair_focus_from_probe(code, snap, None)
        assert out["focused"] is True
        assert out["function_name"] == "inner"
        assert out["probe_sourced"] is True
        assert "探针" in out["hint"] or "probe" in out["hint"].lower()

    def test_probe_ast_parse_failure_returns_unfocused(self):
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "f", "line": 1}]}
        out = dbg._locate_repair_focus_from_probe("def f(:\n", snap, None)
        assert out["focused"] is False


# ─── _build_position_aware_prompt_section 分支 ───────────────────────────────


class TestBuildPositionAwarePromptSectionBranches:
    def test_unfocused_returns_empty(self):
        dbg = _mk_debugger()
        assert dbg._build_position_aware_prompt_section({"focused": False}) == ""

    def test_focused_returns_hint(self):
        dbg = _mk_debugger()
        focus = {"focused": True, "hint": "修复指引：检查 f()"}
        out = dbg._build_position_aware_prompt_section(focus)
        assert "修复指引：检查 f()" in out
        assert out.startswith("\n")

    def test_focused_missing_hint_key_returns_empty_hint(self):
        dbg = _mk_debugger()
        out = dbg._build_position_aware_prompt_section({"focused": True})
        assert out == "\n\n"


# ─── _generate_adversarial_intents 分支 ───────────────────────────────────────


class TestGenerateAdversarialIntentsBranches:
    def _run(self, dbg, raw_response, array_result, object_result=None):
        """在**上下文管理器**内 stub 两级解析路径后调用被测方法。

        T2（2026-10-11 独立评审落地）：本方法的契约是**顶层 JSON 数组**，
        解析顺序为 `extract_json_array` → 回退 `_extract_json`（对象包装）。
        因此需分别 stub 两级，而不是只 stub `_extract_json`（旧实现只走对象
        路径，正是"数组永远解析失败"缺陷的根源）。

        用 `with` 而非 `self._patch.start()`/`tearDown`：后者在同一测试类内
        存在跨用例泄漏（前一个用例启动的 patch 未在下一个无 patch 用例前
        撤销），会让"真实解析链"用例读到上一个用例的返回值。
        """
        dbg._call_llm_with_cache = MagicMock(return_value=raw_response)
        if array_result is None:
            array_patch = MagicMock(side_effect=json.JSONDecodeError("no array", "x", 0))
        else:
            array_patch = MagicMock(return_value=array_result)
        dbg._extract_json = MagicMock(return_value=object_result if object_result is not None else {})
        with patch("src.agents.debugger.extract_json_array", array_patch):
            return dbg._generate_adversarial_intents("code", "RUNTIME")

    def test_list_result_returns_capped_intents(self):
        dbg = _mk_debugger()
        out = self._run(dbg, "raw", ["h1", "h2", "h3", "h4", "h5"])
        assert out == ["h1", "h2", "h3"]  # 上限 3

    def test_json_array_raw_response_parses_via_array_path(self):
        """T2 回归锁：真实 LLM 输出的顶层 JSON 数组必须被解析。

        修复前 `_extract_json`（extract_json_object）只认 `{`，对顶层数组恒抛
        JSONDecodeError，对抗性推理（3.1）因此静默降级为空假设。
        本用例**不打任何补丁**——走真实解析链，确保契约端到端成立。
        """
        dbg = _mk_debugger()
        dbg._call_llm_with_cache = MagicMock(return_value='["a", "b", "c", "d"]')
        assert dbg._generate_adversarial_intents("code", "RUNTIME") == ["a", "b", "c"]

    def test_array_path_unavailable_falls_back_to_object(self):
        """数组路径抛 JSONDecodeError 时必须回退对象包装路径（不吞异常）。"""
        dbg = _mk_debugger()
        out = self._run(dbg, '{"hypotheses": ["z"]}', None, {"hypotheses": ["z"]})
        assert out == ["z"]

    def test_dict_with_hypotheses_key(self):
        dbg = _mk_debugger()
        # 数组路径不可用 → 回退对象包装形态
        out = self._run(dbg, "raw", None, {"hypotheses": ["a", "b"]})
        assert out == ["a", "b"]

    def test_non_list_non_dict_returns_empty(self):
        dbg = _mk_debugger()
        out = self._run(dbg, "raw", None, "just a string")
        assert out == []

    def test_none_result_returns_empty(self):
        dbg = _mk_debugger()
        out = self._run(dbg, "raw", None, None)
        assert out == []

    def test_llm_exception_returns_empty(self):
        dbg = _mk_debugger()
        dbg._call_llm_with_cache = MagicMock(side_effect=RuntimeError("boom"))
        dbg._extract_json = MagicMock(return_value={})
        out = dbg._generate_adversarial_intents("code", "TIMEOUT")
        assert out == []


# ─── _build_adversarial_prompt_section 分支 ──────────────────────────────────


class TestBuildAdversarialPromptSectionBranches:
    def test_multiple_hypotheses(self):
        dbg = _mk_debugger()
        out = dbg._build_adversarial_prompt_section(["h1", "h2"])
        assert "假设 1：h1" in out
        assert "假设 2：h2" in out
        assert "针对性测试用例" in out

    def test_empty_hypotheses(self):
        dbg = _mk_debugger()
        out = dbg._build_adversarial_prompt_section([])
        # 空假设时只有标题行 + 测试用例要求行（无"假设 N：..."编号行）
        assert "对抗性推理" in out
        assert "假设 1" not in out  # 无编号假设行


# ─── _run_critic_eval 分支 ────────────────────────────────────────────────────


class TestRunCriticEvalBranches:
    def _mock_llm(self, dbg, result):
        dbg._call_llm_with_cache = MagicMock(return_value="raw")
        dbg._extract_json = MagicMock(return_value=result)

    def test_break_cases_extracted(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"break_cases": ["c1", "c2", "c3", "c4"], "all_passed": False})
        out = dbg._run_critic_eval("patch", "code", ["h1"])
        assert out["all_passed"] is False
        assert out["break_cases"] == ["c1", "c2", "c3"]  # 上限 3
        assert out["scenarios_checked"] == 1

    def test_no_break_cases_all_passed_default(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"break_cases": []})  # 无 all_passed 字段
        out = dbg._run_critic_eval("patch", "code", ["h1", "h2"])
        assert out["all_passed"] is True  # 无 break_cases → 默认通过
        assert out["scenarios_checked"] == 2

    def test_null_break_cases_treated_as_empty(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"break_cases": None, "all_passed": True})
        out = dbg._run_critic_eval("patch", "code", [])
        assert out["break_cases"] == []
        assert out["all_passed"] is True

    def test_exception_degrades_to_all_passed(self):
        dbg = _mk_debugger()
        dbg._call_llm_with_cache = MagicMock(side_effect=RuntimeError("llm down"))
        dbg._extract_json = MagicMock(return_value={})
        out = dbg._run_critic_eval("patch", "code", ["h"])
        assert out["all_passed"] is True  # 异常降级为未击穿
        assert out["break_cases"] == []
        assert out["intent_hypotheses"] == ["h"]


# ─── _build_critic_feedback 分支 ─────────────────────────────────────────────


class TestBuildCriticFeedbackBranches:
    def test_break_cases_injected(self):
        dbg = _mk_debugger()
        out = dbg._build_critic_feedback({"break_cases": ["case A", "case B"]})
        assert "case A" in out
        assert "case B" in out
        assert "批评者反馈" in out

    def test_empty_break_cases(self):
        dbg = _mk_debugger()
        out = dbg._build_critic_feedback({"break_cases": []})
        assert "批评者反馈" in out
        assert "case" not in out

    def test_missing_break_cases_key(self):
        dbg = _mk_debugger()
        out = dbg._build_critic_feedback({})  # 无 break_cases 键
        assert "批评者反馈" in out


# ─── _run_review_diagnosis 分支 ───────────────────────────────────────────────


class TestRunReviewDiagnosisBranches:
    def _mock_llm(self, dbg, result):
        dbg._call_llm_with_cache = MagicMock(return_value="raw")
        dbg._extract_json = MagicMock(return_value=result)

    def test_implementation_defect(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"defect_type": "implementation_defect", "reason": "逻辑错误"})
        out = dbg._run_review_diagnosis("code", "output", [{"name": "t", "error": "e"}], "ASSERTION")
        assert out["defect_type"] == "implementation_defect"
        assert out["reason"] == "逻辑错误"

    def test_test_defect(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"defect_type": "test_defect", "reason": "预期值写错"})
        out = dbg._run_review_diagnosis("code", "output", [], "ASSERTION")
        assert out["defect_type"] == "test_defect"

    def test_invalid_defect_type_normalized(self):
        """非法 defect_type 保守归一为实现缺陷。"""
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"defect_type": "bogus_value", "reason": "x"})
        out = dbg._run_review_diagnosis("code", "output", [], "UNKNOWN")
        assert out["defect_type"] == "implementation_defect"

    def test_missing_defect_type_defaults_to_implementation(self):
        dbg = _mk_debugger()
        self._mock_llm(dbg, {"reason": "无 defect_type 字段"})
        out = dbg._run_review_diagnosis("code", "output", [], "UNKNOWN")
        assert out["defect_type"] == "implementation_defect"

    def test_exception_degrades_to_implementation(self):
        dbg = _mk_debugger()
        dbg._call_llm_with_cache = MagicMock(side_effect=RuntimeError("down"))
        dbg._extract_json = MagicMock(return_value={})
        out = dbg._run_review_diagnosis("code", "output", [], "UNKNOWN")
        assert out["defect_type"] == "implementation_defect"
        assert out["reason"] == ""

    def test_cases_truncated_to_max_summary(self):
        """失败用例摘要最多 5 条（_MAX_FAILED_CASES_SUMMARY）。

        _run_review_diagnosis 内部构造 query 字符串后经 _call_llm_with_cache
        调用，query 文本含前 5 条用例摘要（t0-t4），t5-t9 被截断。
        """
        dbg = _mk_debugger()
        captured = {}

        def _fake_call(query):
            captured["query"] = query
            return "raw"

        dbg._call_llm_with_cache = _fake_call
        dbg._extract_json = MagicMock(return_value={"defect_type": "implementation_defect", "reason": ""})
        cases = [{"name": f"t{i}", "error": "err" * 50} for i in range(10)]
        dbg._run_review_diagnosis("code", "out", cases, "ASSERTION")
        query = captured["query"]
        # 只取前 5 条用例名（t0-t4），t5 起被截断
        assert "t0" in query and "t4" in query
        assert "t5" not in query
        assert "t9" not in query
