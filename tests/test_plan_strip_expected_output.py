"""A1 消融（plan 去 expected_output）单元测试。

对应审查报告 §5 路径 A1 / §8.6 红队 RT3：
    Planner 读缺陷代码产出 ``test_cases[].expected_output``，Generator 把整段
    plan JSON 灌进 query → 期望值 = 实现当前（错误）行为 → oracle-from-
    implementation → never-red 通道（86/240）抹掉检出。

本测试锁定三件事：
1. **默认关时零行为变化**（同一引用返回，plan_json 逐字节不变）——ADR-0003
   "默认关 = 历史口径不变"纪律；
2. **开启时只剥 expected_output 单变量**，其余键与 logic_analysis 全部保留；
3. **异常/边界保守降级**（非 dict / test_cases 非 list / case 非 dict 时不抛）。
"""

from __future__ import annotations

import json

import pytest

from src.agents.generator import GeneratorAgent, _plan_without_expected_output

PLAN = {
    "function_name": "initials",
    "description": "取姓名首字母",
    "logic_analysis": {
        "input_domain": "非空字符串",
        "output_domain": "大写首字母串",
        "preconditions": ["name 非空"],
        "postconditions": ["返回大写"],
        "edge_cases": ["None 输入"],
    },
    "test_cases": [
        {
            "case_name": "normal_two_words",
            "input_args": {"name": "ada lovelace"},
            "expected_output": "AL",
            "category": "normal",
            "description": "两词姓名",
            "logic_coverage": "C1",
        },
        {
            "case_name": "boundary_none",
            "input_args": {"name": None},
            "expected_output": None,
            "category": "error",
            "description": "None 输入",
            "logic_coverage": "C2",
        },
    ],
}


class TestDefaultOff:
    """默认关：历史口径零变化。"""

    def test_returns_same_object_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", raising=False)
        out = _plan_without_expected_output(PLAN)
        # 同一引用（零拷贝）：不仅是等值，而是 identity
        assert out is PLAN

    def test_payload_unchanged_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", raising=False)
        before = json.dumps(PLAN, ensure_ascii=False, indent=2)
        out = _plan_without_expected_output(PLAN)
        assert json.dumps(out, ensure_ascii=False, indent=2) == before

    @pytest.mark.parametrize("value", ["false", "0", "FALSE", "", "no"])
    def test_falsy_values_keep_disabled(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", value)
        assert _plan_without_expected_output(PLAN) is PLAN


class TestEnabled:
    """开启：只剥 expected_output 单变量。"""

    @pytest.mark.parametrize("value", ["true", "1", "on", "TRUE", "True"])
    def test_truthy_values_enable(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", value)
        out = _plan_without_expected_output(PLAN)
        assert all("expected_output" not in c for c in out["test_cases"])

    def test_expected_output_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        out = _plan_without_expected_output(PLAN)
        assert len(out["test_cases"]) == 2
        for case in out["test_cases"]:
            assert "expected_output" not in case

    def test_other_keys_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """其余单变量必须完整保留——消融的是锚点，不是 plan 结构。"""
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        out = _plan_without_expected_output(PLAN)
        assert out["function_name"] == "initials"
        assert out["logic_analysis"] == PLAN["logic_analysis"]
        assert out["test_cases"][0]["case_name"] == "normal_two_words"
        assert out["test_cases"][0]["input_args"] == {"name": "ada lovelace"}
        assert out["test_cases"][0]["category"] == "normal"
        assert out["test_cases"][0]["logic_coverage"] == "C1"
        assert out["test_cases"][1]["category"] == "error"

    def test_input_plan_not_mutated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """输入对象不得被就地修改（纯函数契约；避免污染 state 中的 plan）。"""
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        snapshot = json.dumps(PLAN, ensure_ascii=False, sort_keys=True)
        _plan_without_expected_output(PLAN)
        assert json.dumps(PLAN, ensure_ascii=False, sort_keys=True) == snapshot
        assert PLAN["test_cases"][0]["expected_output"] == "AL"

    def test_case_without_expected_output_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """本来就没有该键的 case 原样保留（不新增、不删除）。"""
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        plan = {"test_cases": [{"case_name": "only_name"}]}
        out = _plan_without_expected_output(plan)
        assert out["test_cases"] == [{"case_name": "only_name"}]


class TestConservativeDegradation:
    """异常/边界：保守降级，不抛异常。"""

    @pytest.mark.parametrize("bad", [None, "not-a-dict", 42, [], ["a"]])
    def test_non_dict_plan_returned_as_is(self, monkeypatch: pytest.MonkeyPatch, bad: object) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        assert _plan_without_expected_output(bad) is bad

    @pytest.mark.parametrize("bad_cases", [None, "str", 7, {"a": 1}])
    def test_non_list_test_cases_returned_as_is(self, monkeypatch: pytest.MonkeyPatch, bad_cases: object) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        plan = {"test_cases": bad_cases}
        assert _plan_without_expected_output(plan) is plan

    def test_mixed_case_types_do_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        plan = {"test_cases": [{"expected_output": "X", "k": 1}, "raw", 99, None]}
        out = _plan_without_expected_output(plan)
        assert out["test_cases"][0] == {"k": 1}
        assert out["test_cases"][1:] == ["raw", 99, None]

    def test_empty_test_cases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true")
        plan = {"test_cases": []}
        out = _plan_without_expected_output(plan)
        assert out["test_cases"] == []


class TestQueryIntegration:
    """端到端：_build_query 产出的 prompt 文本随开关变化。"""

    def _build(self, monkeypatch: pytest.MonkeyPatch, enabled: bool) -> str:
        monkeypatch.setenv("PLAN_STRIP_EXPECTED_OUTPUT_ENABLE", "true" if enabled else "false")
        agent = GeneratorAgent.__new__(GeneratorAgent)  # 免构造，只测纯构建逻辑
        return agent._build_query(  # type: ignore[attr-defined]
            test_plan=PLAN,
            target_code="def initials(name):\n    return name[0].upper()",
            module_name="mod",
            rag_references=None,
        )

    def test_disabled_query_contains_expected_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        q = self._build(monkeypatch, enabled=False)
        assert "expected_output" in q
        assert "AL" in q

    def test_enabled_query_omits_expected_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        q = self._build(monkeypatch, enabled=True)
        assert "expected_output" not in q
        # 结构保留：函数名 / 用例名 / 逻辑分析仍在 prompt 中
        assert "initials" in q
        assert "normal_two_words" in q
        assert "logic_analysis" in q
        assert "boundary_none" in q
