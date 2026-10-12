"""P0-A-2（2026-10-12 独立评审落地）：规格优先生成（Spec-First Generation）测试。

锁定行为（默认关 = 历史口径零变化，ADR-0003）：
    1. DETECTION_SPEC_MODE 开关三态（off 默认 / replace / 未识别值降级 off）；
    2. build_spec_replace_section 的渲染纪律：签名 + docstring + NL 规约 +
       SpecExpr 子句进产物，**函数体（实现细节）绝不进产物**（misguidance
       effect 缓解的核心：LLM 不得接触实现）；
    3. 无规约材料 → 空串 → 调用方保持历史口径（注入目标代码），不产出
       "无代码无规约"的空洞提示；
    4. _build_query 的 replace 分支：目标代码块被规约文档替换而非并列；
    5. _generator_node 接线：replace 模式把 spec_replace_section 传入
       generate；默认 off 时传 None（历史口径）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.tools.spec_first import build_spec_replace_section, detection_spec_mode

# 带缺陷的被测函数（减法实现冒充加法——oracle-from-implementation 的典型场景）
_BUGGY_CODE = (
    'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a - b  # BUG: should be a + b\n'
)

_FULL_PLAN: dict[str, Any] = {
    "function_name": "add",
    "description": "加法",
    "logic_analysis": {
        "input_domain": "整数对",
        "output_domain": "和",
        "preconditions": ["a、b 为整数"],
        "postconditions": ["返回值等于两数之和"],
        "invariants": ["结果与参数顺序无关"],
        "edge_cases": ["任一参数为 0 时返回另一参数"],
        "preconditions_expr": ["isinstance(a, int) and isinstance(b, int)"],
        "postconditions_expr": ["result == a + b"],
        "invariants_expr": [],
    },
    "test_cases": [
        {"case_name": "normal", "input_args": {"a": 1, "b": 2}, "expected_output": -1},
    ],
}


# ─── 1. 开关三态 ─────────────────────────────────────────────────────────────


class TestDetectionSpecMode:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        assert detection_spec_mode() == "off"

    def test_replace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        assert detection_spec_mode() == "replace"

    @pytest.mark.parametrize("raw", ["on", "true", "1", "bogus", "spec", ""])
    def test_unrecognized_degrades_to_off(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        """未识别值保守降级 off（不认识的模式不得改变行为）。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", raw)
        assert detection_spec_mode() == "off"

    @pytest.mark.parametrize("raw", ["REPLACE", " Replace ", "replace"])
    def test_case_and_space_insensitive(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        """大小写 / 空白归一（与其余开关同口径）。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", raw)
        assert detection_spec_mode() == "replace"


# ─── 2. 规约文档渲染纪律 ─────────────────────────────────────────────────────


class TestBuildSpecReplaceSection:
    def test_full_materials_render_signature_and_specs(self) -> None:
        section = build_spec_replace_section(_FULL_PLAN, _BUGGY_CODE, module_name="mathops", target_function="add")
        assert section, "完整规约材料应产出版面"
        # 签名（含类型注解——注解是规约信息）
        assert "def add(a: int, b: int) -> int" in section
        # docstring（文档化契约）
        assert "Return the sum of a and b." in section
        # NL 规约三段 + 边界
        assert "前置条件：a、b 为整数" in section
        assert "后置条件：返回值等于两数之和" in section
        assert "不变量：结果与参数顺序无关" in section
        assert "边界情况：任一参数为 0 时返回另一参数" in section
        # SpecExpr 形式化子句
        assert "isinstance(a, int) and isinstance(b, int)" in section
        assert "result == a + b" in section
        # 模块名 import 约束
        assert "from mathops import" in section
        # 生成纪律
        assert "oracle-from-implementation" in section

    def test_function_body_never_enters_section(self) -> None:
        """核心纪律：实现细节（函数体）绝不进产物——misguidance effect 缓解的前提。"""
        section = build_spec_replace_section(_FULL_PLAN, _BUGGY_CODE, module_name="mathops", target_function="add")
        # 缺陷实现的特征行不得出现
        assert "return a - b" not in section
        assert "BUG" not in section
        assert "```" not in section  # 不产出代码块（避免诱导照抄实现）
        # 反证：被测源码里确实有这些串（防测试因源串不存在而假通过）
        assert "return a - b" in _BUGGY_CODE

    def test_no_materials_returns_empty(self) -> None:
        """无任何规约材料（含无 docstring）→ 空串（调用方保持历史口径注入目标代码）。"""
        bare_code = "def add(a, b):\n    return a - b\n"  # 无 docstring、无规约字段
        bare_plan = {"function_name": "add", "test_cases": []}
        assert build_spec_replace_section(bare_plan, bare_code, "m", "add") == ""

    def test_none_plan_returns_empty(self) -> None:
        assert build_spec_replace_section(None, _BUGGY_CODE, "m", "add") == ""

    def test_non_dict_plan_returns_empty(self) -> None:
        assert build_spec_replace_section("not a plan", _BUGGY_CODE, "m", "add") == ""

    def test_docstring_only_material_suffices(self) -> None:
        """仅 docstring 可作规约材料（无 NL 字段时仍渲染，不降级为空洞提示）。"""
        plan = {"function_name": "add"}
        section = build_spec_replace_section(plan, _BUGGY_CODE, "m", "add")
        assert "Return the sum of a and b." in section

    def test_signature_extraction_failure_degrades_gracefully(self) -> None:
        """源码语法错误 → 无签名行，但 NL 规约照常渲染（保守降级不空转）。"""
        section = build_spec_replace_section(_FULL_PLAN, "def add(: broken", "m", "add")
        assert "后置条件：返回值等于两数之和" in section
        assert "函数签名：" not in section

    def test_function_name_fallback_to_plan(self) -> None:
        """target_function 缺省时从 test_plan.function_name 回退提取签名。"""
        section = build_spec_replace_section(_FULL_PLAN, _BUGGY_CODE, "m")
        assert "def add(a: int, b: int) -> int" in section


# ─── 3. _build_query 的 replace 分支 ─────────────────────────────────────────


class TestBuildQueryReplaceBranch:
    def _gen(self):
        from src.agents.generator import GeneratorAgent

        return GeneratorAgent()

    def test_replace_swaps_code_block_for_spec_document(self) -> None:
        gen = self._gen()
        section = build_spec_replace_section(_FULL_PLAN, _BUGGY_CODE, "m", "add")
        out = gen._build_query(_FULL_PLAN, _BUGGY_CODE, "m", None, None, spec_replace_section=section)
        # 规约文档进查询
        assert "规格优先模式" in out
        assert "result == a + b" in out
        # 目标代码块被替换（不是并列）
        assert "目标代码：" not in out
        assert "return a - b" not in out

    def test_default_none_keeps_historical_query(self) -> None:
        """spec_replace_section=None（默认）→ 历史口径逐字节不变。"""
        gen = self._gen()
        out = gen._build_query(_FULL_PLAN, _BUGGY_CODE, "m", None, None)
        assert "目标代码：" in out
        assert "return a - b" in out
        assert "规格优先模式" not in out

    def test_empty_string_section_keeps_historical_query(self) -> None:
        """空串 section（无规约材料）→ 历史口径（调用方不产空洞提示）。"""
        gen = self._gen()
        out = gen._build_query(_FULL_PLAN, _BUGGY_CODE, "m", None, None, spec_replace_section="")
        assert "目标代码：" in out
        assert "规格优先模式" not in out

    def test_replace_still_injects_plan_json(self) -> None:
        """replace 模式保留测试计划 JSON（计划是规约的结构化载体）。"""
        gen = self._gen()
        section = build_spec_replace_section(_FULL_PLAN, _BUGGY_CODE, "m", "add")
        out = gen._build_query(_FULL_PLAN, _BUGGY_CODE, "m", None, None, spec_replace_section=section)
        assert "测试计划（JSON）：" in out
        assert json.loads(out.split("测试计划（JSON）：\n", 1)[1].split("\n\n", 1)[0])["function_name"] == "add"


# ─── 4. _generator_node 接线 ────────────────────────────────────────────────


class TestGeneratorNodeWiring:
    """replace 模式经 _generator_node 传入 generate；默认 off 传 None。"""

    def _run_node(self, monkeypatch: pytest.MonkeyPatch, mode: str | None) -> dict[str, Any]:
        from src.graph import nodes as nodes_mod

        captured: dict[str, Any] = {}

        class _StubGenerator:
            def generate(self, test_plan, target_code, **kwargs):
                captured.update(kwargs)
                captured["test_plan"] = test_plan
                captured["target_code"] = target_code
                return "def test_add():\n    assert add(1, 2) == 3\n"

        monkeypatch.setattr(nodes_mod, "get_or_create_agent", lambda cls: _StubGenerator())
        state = {
            "target_code": _BUGGY_CODE,
            "target_function": "add",
            "module_name": "mathops",
            "test_plan": _FULL_PLAN,
            "iteration": 0,
        }
        if mode is None:
            monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        else:
            monkeypatch.setenv("DETECTION_SPEC_MODE", mode)
        # 关闭同节点其它可选增强，隔离被测开关（默认关，显式确保）
        for env in (
            "BRANCH_COVERAGE_INJECT_ENABLE",
            "BOUNDARY_TRIPLETS_ENABLE",
            "PATH_ENUM_INJECT_ENABLE",
            "OPERATION_MAP_INJECT_ENABLE",
            "ORACLE_VALIDATE_ENABLE",
            "EMPTY_PLAN_SHORTCUT_ENABLE",
        ):
            monkeypatch.delenv(env, raising=False)
        nodes_mod._generator_node(state)
        return captured

    def test_replace_mode_passes_section(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._run_node(monkeypatch, "replace")
        section = captured.get("spec_replace_section")
        assert section, "replace 模式应把规约文档传入 generate"
        assert "result == a + b" in section
        assert "return a - b" not in section

    def test_default_mode_passes_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._run_node(monkeypatch, None)
        assert captured.get("spec_replace_section") is None, "默认 off 时必须传 None（历史口径）"
