#!/usr/bin/env python3
"""M-1（2026-10-17，L 轮 replace 阴性结论后续假设）：规格**增广**臂回归锁定。

锁定七组行为（对应 task-6 / 预注册 §2.1）：

1. ``DETECTION_SPEC_MODE`` 第三值 ``augment``：env / 线程覆盖均接受；大小写 /
   空白归一；未知值仍回落 off 并 warning；
2. ``src.tools.spec_first.build_spec_augment_section``：
   - 与 replace 共享材料抽取 / 主体渲染管线（签名 / 模块名 / 规格锚 /
     docstring / NL / SpecExpr 顺序一致），framing 明确"规格锚与目标代码
     **并列**、请结合两者、实现与规格不一致时按规格构造期望值"；
   - **不得**出现 replace 专属"本提示刻意不包含实现代码"措辞；
   - 函数体不进入段落（代码由 code block 注入）；无非空材料 → 空串
     （``node.py`` 空 human_spec 键回落 df 口径）；确定性；签名失败保守降级；
3. **金标记**：不带/带 human_spec 的既有 replace 渲染逐字节不变
   （期望字符串固化字面量，护住 df_spec / L 轮历史工件可复现性）；
4. ``GeneratorAgent._build_query``：``spec_augment_section`` 非空时在 code block
   之后作为独立段追加（代码完整保留）；None / 空串时**历史查询逐字节不变**
   （固化完整 query 金标记）；
5. ``GeneratorAgent.generate``：新增参数默认 None 走历史路径（金标记硬断言），
   非空时 query 同时包含缺陷代码与规格锚；
6. ``_generator_node`` 接线：mode=augment 构建增广段并写
   ``spec_augment_applied``（attempted_augmented / attempted_fallback）；replace
   模式该字段恒 None（互斥）；minimal 消融档不构建；state 键声明 / 默认值 /
   结果行两处透出；
7. ``experiments.run_benchmark``：注册 ``plain_llm_df_doc_augment`` 臂（复用
   参数化 runner，spec_mode="augment"，默认 DOCSTRING_ANCHOR_TABLE）；命中
   注入锚材料 + 线程覆盖 augment + 检出优先；表缺失逐任务回落 df 不 crash；
   既有 doc / union 两臂仍为 replace（行为不变）；未新增环境变量。

全部测试零 LLM / 零网络 / 确定性。
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.tools.spec_first import (
    _SPEC_MODES,
    build_spec_augment_section,
    build_spec_replace_section,
    detection_spec_mode,
    set_spec_mode_thread_override,
)

# ─── 金标记 1：既有 replace 渲染的完整期望字符串 ───────────────────────────
# 本字面量来自 L 轮入库实现（git show ef90281:src/tools/spec_first.py）冻结；
# 测试**不**动态 import 旧版——锁的是"历史工件可复现性"，不是实现细节。
_GOLDEN_HEADER = [
    "【规格优先模式（Spec-First）：本提示刻意不包含实现代码】",
    "请仅依据以下规约文档与函数签名生成测试。实现细节未知且**不得臆测**——",
    "照猜想中的实现行为写断言（oracle-from-implementation）会系统性抹掉缺陷检出，",
    "是本模式要杜绝的首要失败形态。",
    "",
]
_GOLDEN_CODE = (
    'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a - b  # BUG: should be a + b\n'
)
_GOLDEN_PLANNER_MATERIAL: dict[str, Any] = {
    "function_name": "add",
    "logic_analysis": {
        "preconditions": ["a、b 为整数"],
        "postconditions": ["返回值等于两数之和"],
        "invariants": ["结果与参数顺序无关"],
        "edge_cases": ["任一参数为 0 时返回另一参数"],
        "preconditions_expr": ["isinstance(a, int) and isinstance(b, int)"],
        "postconditions_expr": ["result == a + b"],
        "invariants_expr": [],
    },
}
_GOLDEN_DISCIPLINE = [
    "",
    "【生成纪律】",
    "1. 每个测试必须断言上述规约中可判定的性质（后置 / 不变量 / 边界）；",
    "2. 期望值只能来自规约与 docstring 约定；规约未覆盖的行为禁止臆造具体值——",
    "   改用记录实际行为的探索性断言并在 docstring 标注需人工确认；",
    "3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；",
    "4. 不得访问规约与签名之外的属性 / 符号。",
]
_GOLDEN_REPLACE_SECTION = "\n".join(
    [
        *_GOLDEN_HEADER,
        "函数签名：def add(a: int, b: int) -> int",
        "被测模块名：mathops（import 必须 `from mathops import ...`）",
        "",
        "【文档化契约（docstring）】",
        "Return the sum of a and b.",
        "",
        "【自然语言规约（期望值的唯一合法来源）】",
        "- 前置条件：a、b 为整数",
        "- 后置条件：返回值等于两数之和",
        "- 不变量：结果与参数顺序无关",
        "- 边界情况：任一参数为 0 时返回另一参数",
        "",
        "【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】",
        "- 前置（可执行）：isinstance(a, int) and isinstance(b, int)",
        "- 后置（可执行）：result == a + b",
        *_GOLDEN_DISCIPLINE,
    ]
)
_GOLDEN_SMALL_CODE = "def fn(x):\n    return x - 1\n"
_GOLDEN_SMALL_MATERIAL: dict[str, Any] = {
    "function_name": "fn",
    "logic_analysis": {"postconditions": ["返回 x"], "postconditions_expr": ["result == x"]},
}
_GOLDEN_SMALL_SECTION = "\n".join(
    [
        *_GOLDEN_HEADER,
        "函数签名：def fn(x)",
        "被测模块名：m（import 必须 `from m import ...`）",
        "",
        "【自然语言规约（期望值的唯一合法来源）】",
        "- 后置条件：返回 x",
        "",
        "【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】",
        "- 后置（可执行）：result == x",
        *_GOLDEN_DISCIPLINE,
    ]
)

# ─── 金标记 2：历史（两参数均 None）_build_query 的完整期望字符串 ───────────
_BUGGY_ADD = (
    'def add(a: int, b: int) -> int:\n    """Return the sum of a and b."""\n    return a - b  # BUG: should be a + b\n'
)
_HISTORIC_PLAN: dict[str, Any] = {"function_name": "add", "test_cases": []}
_GOLDEN_HISTORIC_QUERY = (
    "测试计划（JSON）：\n"
    "{\n"
    '  "function_name": "add",\n'
    '  "test_cases": []\n'
    "}\n\n"
    "目标代码：\n"
    "```\n"
    "def add(a: int, b: int) -> int:\n"
    '    """Return the sum of a and b."""\n'
    "    return a - b  # BUG: should be a + b\n"
    "\n"
    "```\n\n"
    "被测模块名：mathops\n\n"
    "请根据以上计划生成完整的 pytest 测试代码。\n\n"
    "【重要约束】import 语句必须使用以下模块名：`mathops`，即 `from mathops import ...`"
)

# 参与各测试的规格材料（含人类独立锚）
_AUGMENT_MATERIAL: dict[str, Any] = {
    "function_name": "add",
    "human_spec": "Input:\n    a: an int\n    b: an int\n\nOutput:\n    The sum of a and b",
    "logic_analysis": {
        "preconditions": ["a、b 为整数"],
        "postconditions": ["返回值等于两数之和"],
        "postconditions_expr": ["result == a + b"],
        "edge_cases": ["任一参数为 0 时返回另一参数"],
    },
}
_BARE_CODE = "def fn(x):\n    return x\n"  # 无 docstring
_BARE_PLAN: dict[str, Any] = {"function_name": "fn", "test_cases": []}

# 未识别模式串（保守降级断言用）
_UNKNOWN_MODES = ("on", "true", "1", "bogus", "spec", "augmented", "AUGMENT-EXTRA")


def _gen():
    from src.agents.generator import GeneratorAgent

    return GeneratorAgent()


# ─── 0. 隔离：线程覆盖 / 本测试无关开关 ────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_spec_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空线程覆盖 + 规格开关（防跨测试残留；其余增强开关默认关）。"""
    set_spec_mode_thread_override(None)
    monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
    monkeypatch.delenv("ORACLE_CONTEXT_TIER", raising=False)
    yield
    set_spec_mode_thread_override(None)


# ─── 1. 模式解析（第三值 augment）───────────────────────────────────────────
class TestDetectionSpecModeAugment:
    @pytest.mark.unit
    def test_augment_is_valid_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        assert detection_spec_mode() == "augment"
        assert "augment" in _SPEC_MODES

    @pytest.mark.unit
    def test_replace_still_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        assert detection_spec_mode() == "replace"

    @pytest.mark.unit
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        assert detection_spec_mode() == "off"

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", ["AUGMENT", " Augment ", "  augment\t"])
    def test_case_and_space_insensitive(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", raw)
        assert detection_spec_mode() == "augment"

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", _UNKNOWN_MODES)
    def test_unrecognized_degrades_to_off(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知值保守降级 off（不认识的模式不得改变行为），且记 warning。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", raw)
        assert detection_spec_mode() == "off"
        assert any("未识别" in record.message for record in caplog.records)

    @pytest.mark.unit
    def test_empty_env_value_defaults_off_without_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """空串 env = 未设（历史口径 off），不是"未识别值"，不应告警。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", "")
        assert detection_spec_mode() == "off"
        assert not any("未识别" in record.message for record in caplog.records)

    @pytest.mark.unit
    def test_thread_override_augment_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "off")
        set_spec_mode_thread_override("augment")
        try:
            assert detection_spec_mode() == "augment"
        finally:
            set_spec_mode_thread_override(None)
        assert detection_spec_mode() == "off"

    @pytest.mark.unit
    def test_invalid_override_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        set_spec_mode_thread_override("bogus")
        try:
            assert detection_spec_mode() == "augment"
        finally:
            set_spec_mode_thread_override(None)


# ─── 2. build_spec_augment_section 渲染 ────────────────────────────────────
class TestBuildSpecAugmentSection:
    @pytest.mark.unit
    def test_full_materials_render_anchor_and_specs(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert section
        assert "def add(a: int, b: int) -> int" in section  # 签名
        assert "from mathops import" in section  # 模块名约束
        assert "Input:" in section and "Output:" in section  # 人类独立锚
        assert "Return the sum of a and b." in section  # 文档化契约
        assert "后置条件：返回值等于两数之和" in section  # NL 规约
        assert "result == a + b" in section  # SpecExpr 子句

    @pytest.mark.unit
    def test_framing_phrases_present(self) -> None:
        """预注册 §2.1 锁定的 framing（并列 / 结合两者 / 按规格构造期望值）。"""
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert "规格锚与目标代码并列" in section
        assert "请结合两者" in section
        assert "当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。" in section
        assert "上方已完整给出目标代码" in section

    @pytest.mark.unit
    def test_no_replace_only_phrasing(self) -> None:
        """增广段不得复用 replace 的"不包含实现代码"措辞（语义冲突）。"""
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert "本提示刻意不包含实现代码" not in section
        assert "请仅依据以下规约文档与函数签名生成测试" not in section

    @pytest.mark.unit
    def test_function_body_never_enters_section(self) -> None:
        """段落只含规格材料；实现体由调用方 code block 注入（不进本段）。"""
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert "return a - b" not in section
        assert "BUG" not in section
        assert "```" not in section

    @pytest.mark.unit
    def test_shared_pipeline_with_replace_before_discipline(self) -> None:
        """共享材料抽取 / 主体渲染：两模式在【生成纪律】之前逐字节相同。"""

        def _body(section: str) -> str:
            return section.split("\n【生成纪律", 1)[0].split("函数签名：", 1)[1]

        aug = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        rep = build_spec_replace_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert _body(aug) == _body(rep)
        # 但分帧与纪律不同（不是同一字符串）
        assert aug != rep
        assert "【规格增广模式（Spec-Augment）" in aug
        assert "【规格优先模式（Spec-First）" in rep

    @pytest.mark.unit
    def test_human_spec_rendered_before_docstring(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert section.index("【独立于实现的规格锚（人类 docstring）】") < section.index("【文档化契约（docstring）】")

    @pytest.mark.unit
    def test_none_plan_returns_empty(self) -> None:
        assert build_spec_augment_section(None, _BUGGY_ADD, "mathops", "add") == ""

    @pytest.mark.unit
    def test_non_dict_plan_returns_empty(self) -> None:
        assert build_spec_augment_section("not a plan", _BUGGY_ADD, "mathops", "add") == ""

    @pytest.mark.unit
    def test_no_material_returns_empty(self) -> None:
        """无 docstring、无锚、无规约 → 空串（调用方保持纯 df 代码口径）。"""
        assert build_spec_augment_section(_BARE_PLAN, _BARE_CODE, "m", "fn") == ""

    @pytest.mark.unit
    def test_empty_human_spec_key_alone_returns_empty(self) -> None:
        """node.py 语义：仅 human_spec 空键（无其他材料）→ 空串（回落 df），
        与 replace 的"键在场即材料"不同（augment 只认真实非空内容）。"""
        material = {"function_name": "", "human_spec": ""}
        node_code = "class Node:\n    def __init__(self, value=None):\n        self.value = value\n"
        assert build_spec_augment_section(material, node_code, "node", "") == ""
        # 对照：replace 键在场即渲染（历史锚臂语义，未变）
        assert build_spec_replace_section(material, node_code, "node", "") != ""

    @pytest.mark.unit
    def test_nonempty_human_spec_alone_suffices(self) -> None:
        material = {"function_name": "fn", "human_spec": "ANCHOR_ONLY_MARKER"}
        section = build_spec_augment_section(material, _BARE_CODE, "m", "fn")
        assert "ANCHOR_ONLY_MARKER" in section

    @pytest.mark.unit
    def test_docstring_only_material_suffices(self) -> None:
        section = build_spec_augment_section({"function_name": "add"}, _BUGGY_ADD, "mathops", "add")
        assert "Return the sum of a and b." in section

    @pytest.mark.unit
    def test_deterministic_repeat(self) -> None:
        first = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        second = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert first == second
        assert first == build_spec_augment_section(dict(_AUGMENT_MATERIAL), _GOLDEN_CODE, "mathops", "add")

    @pytest.mark.unit
    def test_signature_failure_degrades_without_raising(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, "def add(: broken", "mathops", "add")
        assert section
        assert "函数签名：" not in section
        assert "后置条件：返回值等于两数之和" in section

    @pytest.mark.unit
    def test_target_function_fallback_to_plan(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops")
        assert "def add(a: int, b: int) -> int" in section


# ─── 3. 金标记：replace 渲染逐字节不变 ─────────────────────────────────────
class TestReplaceGoldenUnchanged:
    @pytest.mark.unit
    def test_planner_material_golden_byte_identical(self) -> None:
        section = build_spec_replace_section(_GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert section == _GOLDEN_REPLACE_SECTION

    @pytest.mark.unit
    def test_small_material_golden_byte_identical(self) -> None:
        section = build_spec_replace_section(_GOLDEN_SMALL_MATERIAL, _GOLDEN_SMALL_CODE, "m", "fn")
        assert section == _GOLDEN_SMALL_SECTION

    @pytest.mark.unit
    def test_augment_call_does_not_mutate_replace_output(self) -> None:
        before = build_spec_replace_section(_GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        after = build_spec_replace_section(_GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert before == after == _GOLDEN_REPLACE_SECTION

    @pytest.mark.unit
    def test_replace_with_human_spec_key_still_renders_anchor(self) -> None:
        """带 human_spec 的 replace 渲染未变：锚段在 docstring 之前、帧头仍是 replace。"""
        section = build_spec_replace_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        assert section.startswith("【规格优先模式（Spec-First）：本提示刻意不包含实现代码】\n")
        assert "【独立于实现的规格锚（人类 docstring）】" in section
        assert section.index("【独立于实现的规格锚（人类 docstring）】") < section.index("【文档化契约（docstring）】")


# ─── 4. _build_query：增广段位置 + 历史路径金标记 ──────────────────────────
class TestBuildQueryAugmentBranch:
    @pytest.mark.unit
    def test_augment_appended_after_code_block(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        out = _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None, spec_augment_section=section)
        # 代码完整保留
        assert "目标代码：" in out
        assert "return a - b" in out
        assert "```" in out
        # 规格锚同时出现，且位于 code block 之后、"被测模块名"之前
        assert "【规格增广模式（Spec-Augment）" in out
        assert (
            out.index("return a - b") < out.index("【规格增广模式（Spec-Augment）") < out.index("被测模块名：mathops")
        )

    @pytest.mark.unit
    def test_augment_query_not_replace_semantics(self) -> None:
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        out = _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None, spec_augment_section=section)
        assert "规格优先模式" not in out
        assert "本提示刻意不包含实现代码" not in out

    @pytest.mark.unit
    def test_default_none_query_byte_identical_golden(self) -> None:
        """spec_augment_section 缺省（不传）→ 历史查询逐字节不变（硬断言）。"""
        assert _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None) == _GOLDEN_HISTORIC_QUERY

    @pytest.mark.unit
    def test_explicit_none_query_byte_identical_golden(self) -> None:
        out = _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None, spec_augment_section=None)
        assert out == _GOLDEN_HISTORIC_QUERY

    @pytest.mark.unit
    def test_empty_string_query_byte_identical_golden(self) -> None:
        out = _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None, spec_augment_section="")
        assert out == _GOLDEN_HISTORIC_QUERY

    @pytest.mark.unit
    def test_replace_branch_query_golden_unchanged(self) -> None:
        """replace 参数的既有行为不变：code block 被替换、不追加增广段。"""
        section = build_spec_replace_section(_GOLDEN_PLANNER_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        out = _gen()._build_query(_HISTORIC_PLAN, _GOLDEN_CODE, "mathops", None, None, spec_replace_section=section)
        assert section in out
        assert "目标代码：" not in out
        assert "return a - b" not in out


# ─── 5. generate()：spec_augment_section 参数路径 ──────────────────────────
class TestGenerateAugmentPath:
    def _capture(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        from src.agents.generator import GeneratorAgent

        captured: dict[str, Any] = {"queries": []}

        def _fake_call(self, query, temperature=None, complexity_class=None):
            captured["queries"].append(query)
            return "def test_add():\n    assert add(1, 2) == 3\n"

        monkeypatch.setattr(GeneratorAgent, "_call_llm_with_cache", _fake_call)
        return captured

    @pytest.mark.unit
    def test_generate_default_none_historical_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """generate() 缺省（新参数 None）→ 历史 query 逐字节不变（硬断言）。"""
        captured = self._capture(monkeypatch)
        _gen().generate(_HISTORIC_PLAN, _GOLDEN_CODE, module_name="mathops")
        assert captured["queries"] == [_GOLDEN_HISTORIC_QUERY]

    @pytest.mark.unit
    def test_generate_explicit_none_historical_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._capture(monkeypatch)
        _gen().generate(_HISTORIC_PLAN, _GOLDEN_CODE, module_name="mathops", spec_augment_section=None)
        assert captured["queries"] == [_GOLDEN_HISTORIC_QUERY]

    @pytest.mark.unit
    def test_generate_augment_keeps_code_and_adds_anchor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._capture(monkeypatch)
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        _gen().generate(_HISTORIC_PLAN, _GOLDEN_CODE, module_name="mathops", spec_augment_section=section)
        query = captured["queries"][0]
        assert "return a - b" in query  # 缺陷代码仍在
        assert "【规格增广模式（Spec-Augment）" in query  # 规格锚并列追加
        assert query.index("return a - b") < query.index("【规格增广模式（Spec-Augment）")

    @pytest.mark.unit
    def test_generate_returns_code_unchanged_by_augment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._capture(monkeypatch)
        section = build_spec_augment_section(_AUGMENT_MATERIAL, _GOLDEN_CODE, "mathops", "add")
        code = _gen().generate(_HISTORIC_PLAN, _GOLDEN_CODE, module_name="mathops", spec_augment_section=section)
        assert captured["queries"]  # LLM 调用发生
        assert "def test_add" in code


# ─── 6. _generator_node 接线 ───────────────────────────────────────────────
_OPTIONAL_ENVS = (
    "BRANCH_COVERAGE_INJECT_ENABLE",
    "BOUNDARY_TRIPLETS_ENABLE",
    "PATH_ENUM_INJECT_ENABLE",
    "OPERATION_MAP_INJECT_ENABLE",
    "ORACLE_VALIDATE_ENABLE",
    "EMPTY_PLAN_SHORTCUT_ENABLE",
    "REPRO_TEST_ENABLE",
    "FEEDBACK_COMPRESSION_ENABLE",
    "DETECTION_FIRST_SECTION_ENABLE",
    "INJECTION_GUARD_ENABLE",
)


def _state(code: str, *, anchor: dict[str, Any] | None = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    from src.graph.state import create_initial_state

    state = create_initial_state("u_aug", "target_mod.py", code, 1, module_name="mathops", target_function="add")
    state["test_plan"] = plan
    if anchor is not None:
        state["spec_anchor"] = anchor
    return dict(state)


def _run_generator(monkeypatch: pytest.MonkeyPatch, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.graph import nodes as nodes_mod

    captured: dict[str, Any] = {}

    class _StubGenerator:
        def generate(self, test_plan, target_code, **kwargs):
            captured["test_plan"] = test_plan
            captured["target_code"] = target_code
            captured.update(kwargs)
            return "def test_x():\n    assert True\n"

    monkeypatch.setattr(nodes_mod, "get_or_create_agent", lambda cls: _StubGenerator())
    monkeypatch.setattr(nodes_mod, "ENABLE_RAG", False)
    for env in _OPTIONAL_ENVS:
        monkeypatch.delenv(env, raising=False)
    update = nodes_mod._generator_node(state)
    return update, captured


class TestGeneratorNodeAugmentWiring:
    @pytest.mark.unit
    def test_augment_with_anchor_attempted_augmented(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        state = _state(_GOLDEN_CODE, anchor=_AUGMENT_MATERIAL)
        update, captured = _run_generator(monkeypatch, state)
        assert update["spec_augment_applied"] == "attempted_augmented"
        section = captured.get("spec_augment_section")
        assert section and "Input:" in section and "当实现与规格不一致时" in section
        # 互斥：replace 段不得同时构建
        assert update["spec_replace_applied"] is None
        assert captured.get("spec_replace_section") is None

    @pytest.mark.unit
    def test_augment_without_material_attempted_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 docstring / 无锚材料 → attempted_fallback + 传 None（纯 df 口径）。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        update, captured = _run_generator(monkeypatch, _state(_BARE_CODE))
        assert update["spec_augment_applied"] == "attempted_fallback"
        assert captured.get("spec_augment_section") is None

    @pytest.mark.unit
    def test_augment_anchor_preferred_over_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        plan = {
            "function_name": "add",
            "logic_analysis": {"postconditions": ["PLAN_MARKER 计划侧材料"]},
            "test_cases": [{"case_name": "b", "input_args": "(1)", "expected_output": "1", "category": "basic"}],
        }
        anchor = {"function_name": "add", "human_spec": "ANCHOR_MARKER 锚侧材料"}
        update, captured = _run_generator(monkeypatch, _state(_GOLDEN_CODE, anchor=anchor, plan=plan))
        assert update["spec_augment_applied"] == "attempted_augmented"
        section = captured["spec_augment_section"]
        assert "ANCHOR_MARKER" in section
        assert "PLAN_MARKER" not in section

    @pytest.mark.unit
    def test_replace_mode_augment_field_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        update, captured = _run_generator(monkeypatch, _state(_GOLDEN_CODE, anchor=_AUGMENT_MATERIAL))
        assert update["spec_replace_applied"] == "attempted_replaced"
        assert update["spec_augment_applied"] is None
        assert captured.get("spec_augment_section") is None

    @pytest.mark.unit
    def test_default_off_both_fields_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        update, captured = _run_generator(monkeypatch, _state(_GOLDEN_CODE, anchor=_AUGMENT_MATERIAL))
        assert update["spec_replace_applied"] is None
        assert update["spec_augment_applied"] is None
        assert captured.get("spec_augment_section") is None
        assert captured.get("spec_replace_section") is None

    @pytest.mark.unit
    def test_unknown_mode_both_fields_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "bogus")
        update, _ = _run_generator(monkeypatch, _state(_GOLDEN_CODE, anchor=_AUGMENT_MATERIAL))
        assert update["spec_augment_applied"] is None
        assert update["spec_replace_applied"] is None

    @pytest.mark.unit
    def test_minimal_context_tier_skips_augment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ORACLE_CONTEXT_MINIMAL 消融档不构建任何额外段（历史口径）。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        monkeypatch.setenv("ORACLE_CONTEXT_TIER", "minimal")
        update, captured = _run_generator(monkeypatch, _state(_GOLDEN_CODE, anchor=_AUGMENT_MATERIAL))
        assert update["spec_augment_applied"] is None
        assert captured.get("spec_augment_section") is None

    @pytest.mark.unit
    def test_update_dict_always_contains_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "augment")
        update, _ = _run_generator(monkeypatch, _state(_BARE_CODE))
        assert "spec_augment_applied" in update


# ─── 7. state 契约 + 结果行透出 ────────────────────────────────────────────
class TestStateAndResultRow:
    @pytest.mark.unit
    def test_state_annotation_declared(self) -> None:
        from src.graph.state import AITesterState

        assert "spec_augment_applied" in AITesterState.__annotations__

    @pytest.mark.unit
    def test_initial_state_default_none(self) -> None:
        from src.graph.state import create_initial_state

        state = create_initial_state("u", "m.py", "x = 1\n", 1)
        assert state["spec_augment_applied"] is None

    @pytest.mark.unit
    def test_result_row_reads_state_value(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        task = _make_task()
        row = rb._build_task_result(task, 1.0, final_state={"spec_augment_applied": "attempted_augmented"})
        assert row["spec_augment_applied"] == "attempted_augmented"

    @pytest.mark.unit
    def test_result_row_failure_branch_none(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        row = rb._build_task_result(_make_task(), 1.0, diagnosis="异常", error_category="error")
        assert row["spec_augment_applied"] is None

    @pytest.mark.unit
    def test_result_row_keys_same_both_branches(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        success = rb._build_task_result(_make_task(), 1.0, final_state={"test_passed": True})
        failure = rb._build_task_result(_make_task(), 1.0)
        assert set(success) == set(failure)
        assert "spec_augment_applied" in success and "spec_augment_applied" in failure

    @pytest.mark.unit
    def test_run_benchmark_source_has_both_placements(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        src = Path(rb.__file__).read_text(encoding="utf-8")
        assert '"spec_augment_applied": final_state.get("spec_augment_applied")' in src
        assert '"spec_augment_applied": None' in src


def _make_task():
    from src.datasets.dataset_loader import BenchmarkTask

    return BenchmarkTask(
        task_id="repo__repo-1",
        repo_name="repo/repo",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "test"},
    )


# ─── 8. run_benchmark 臂注册 / 模式覆盖 / 锚表回落 ─────────────────────────
class _FakeGraph:
    """记录 invoke 入参与调用期间关键开关状态的假图。"""

    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        import config as _cfg

        self._sink["invoke_state"] = dict(state)
        self._sink["spec_mode_during"] = detection_spec_mode()
        self._sink["detection_first_during"] = _cfg.detection_first_enabled()
        return dict(state)


def _rb():
    return importlib.import_module("experiments.run_benchmark")


def _sha360(source: str) -> str:
    return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()


def _make_state(target_code: str) -> dict[str, Any]:
    from src.graph.state import create_initial_state

    state = create_initial_state("u_doc_augment", "target_mod.py", target_code, 1, module_name="target_mod")
    state["task_id"] = "quixbugs__bitcount"
    return dict(state)


def _write_anchor_table(path: Path, source: str, material: dict[str, Any]) -> Path:
    path.write_text(json.dumps({"meta": {}, "anchors": {_sha360(source): material}}), encoding="utf-8")
    return path


class TestRunBenchmarkAugmentArm:
    @pytest.mark.unit
    def test_registry_entry_present(self) -> None:
        rb = _rb()
        assert "plain_llm_df_doc_augment" in rb.BASELINE_REGISTRY
        assert rb.BASELINE_REGISTRY["plain_llm_df_doc_augment"] is rb.run_plain_llm_df_doc_augment_baseline

    @pytest.mark.unit
    def test_shared_runner_defaults_to_replace(self) -> None:
        import inspect

        sig = inspect.signature(_rb()._run_plain_llm_df_anchor_baseline)
        assert sig.parameters["spec_mode"].default == "replace"

    @pytest.mark.unit
    def test_arm_hit_injects_anchor_and_augment_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import config as _cfg

        rb = _rb()
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
        monkeypatch.delenv("DOC_ANCHOR_TABLE", raising=False)
        source = "def fn(x):\n    return x + 1\n"
        material = {"function_name": "fn", "human_spec": "SPEC_MARKER"}
        table_path = _write_anchor_table(tmp_path / "t.json", source, material)
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_DEFAULT", str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        result = rb.run_plain_llm_df_doc_augment_baseline(_make_state(source))

        assert sink["invoke_state"]["spec_anchor"] == material
        assert sink["spec_mode_during"] == "augment"
        assert sink["detection_first_during"] is True
        assert result["spec_anchor"] == material
        # finally 全恢复
        assert detection_spec_mode() == "off"
        assert _cfg.detection_first_enabled() is False

    @pytest.mark.unit
    def test_arm_miss_falls_back_without_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = _rb()
        monkeypatch.delenv("DOC_ANCHOR_TABLE", raising=False)
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_DEFAULT", str(tmp_path / "nope.json"))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        rb.run_plain_llm_df_doc_augment_baseline(_make_state("def unknown():\n    return 0\n"))

        assert sink["invoke_state"]["spec_anchor"] is None  # 回落 df 口径
        assert sink["spec_mode_during"] == "augment"  # 节点渲染空串 → attempted_fallback
        assert detection_spec_mode() == "off"  # finally 恢复

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("baseline_attr", "mode"),
        [
            ("run_plain_llm_df_doc_baseline", "replace"),
            ("run_plain_llm_df_doc_union_baseline", "replace"),
            ("run_plain_llm_df_doc_augment_baseline", "augment"),
        ],
    )
    def test_existing_arms_spec_mode_unchanged(
        self, baseline_attr: str, mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """既有 doc / union 臂仍为 replace；新增 augment 臂为 augment。"""
        rb = _rb()
        monkeypatch.delenv("DOC_ANCHOR_TABLE", raising=False)
        source = "def fn(x):\n    return x + 1\n"
        material = {"function_name": "fn", "human_spec": "S"}
        table_path = _write_anchor_table(tmp_path / "t.json", source, material)
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_DEFAULT", str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_UNION_DEFAULT", str(table_path))
        monkeypatch.setattr(rb, "_DOC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        getattr(rb, baseline_attr)(_make_state(source))

        assert sink["spec_mode_during"] == mode

    @pytest.mark.unit
    def test_augment_arm_uses_default_doc_table(self) -> None:
        rb = _rb()
        assert rb._DOC_ANCHOR_TABLE_DEFAULT.endswith(
            "/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json"
        )

    @pytest.mark.unit
    def test_no_new_env_var_for_augment(self) -> None:
        """augment 复用既有 DETECTION_SPEC_MODE 开关——spec_first 不得新增环境变量。"""
        spec_first = Path(__file__).resolve().parent.parent / "src" / "tools" / "spec_first.py"
        tree = ast.parse(spec_first.read_text(encoding="utf-8"))
        env_names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if "ENV" in name and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    env_names.add(node.value.value)
        assert env_names == {"DETECTION_SPEC_MODE"}

    @pytest.mark.unit
    def test_env_snapshot_keys_contain_spec_mode(self) -> None:
        rb = _rb()
        tree = ast.parse(Path(rb.__file__).read_text(encoding="utf-8"))
        keys: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_env_snapshot_keys" for t in node.targets
            ):
                keys = [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        assert "DETECTION_SPEC_MODE" in keys
        assert "DOC_ANCHOR_TABLE" in keys
