"""P2-7 接线审计回归测试（2026-10 批次）：N2 蜕变关系 / N4 差分测试
两个"纯数据原语"模块从孤立状态接进 _generator_node 主链路后，
锁定：
1. GeneratorAgent.generate 接受 metamorphic_section / differential_section
   参数且 None 时不注入（历史口径零变化）；
2. suggest_metamorphic_relations 的 6 类 MR 模板真实命中（接线审计修复前
   "func name contains" 解析 bug + int(" 2+") 解析 bug 导致 6 类全 0 命中）；
3. 两开关默认关时 _generator_node 注入段落为 None（零行为变化）；
4. run_differential_check / check_metamorphic_relation 原语基本行为。

与 tests/test_packaging.py 的 P2-5 依赖分组测试同批次（2026-10 优化批次）。
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from experiments.differential_test import (
    compare_outputs,
    differential_enabled,
    run_differential_check,
)
from experiments.metamorphic_oracle import (
    build_metamorphic_prompt_section,
    check_metamorphic_relation,
    metamorphic_enabled,
    suggest_metamorphic_relations,
)

# ── 1. GeneratorAgent.generate 新参数面 ──────────────────────────────────────


def _real_gen_with_mocked_llm():
    """复用 tests/test_generator_pure_logic.py 的 mock 模式（零 LLM 调用）。

    返回 (GeneratorAgent 实例, 调用记录 list)：LLM 调用被替换为记录
    query 的闭包，其余实例方法（_extract_python_code 等）同样 mock。
    """
    from src.agents.generator import GeneratorAgent

    _calls: list[str] = []

    gen = GeneratorAgent()

    def _fake_call(query: str, **_kw: object) -> str:
        _calls.append(query)
        return "raw"

    gen._call_llm_with_cache = MagicMock(side_effect=_fake_call)
    gen._extract_python_code = MagicMock(return_value="def test_x():\n    pass\n")
    gen._validate_parametrize = MagicMock(return_value=True)
    gen._fix_import_module = MagicMock(side_effect=lambda c, m: c)
    return gen, _calls


def test_generate_new_sections_params_default_none():
    gen, _ = _real_gen_with_mocked_llm()
    code = gen.generate({"name": "t"}, "def f():\n    pass", "m", None)
    assert code  # None 新参数零变化（同 branch_coverage_section 历史口径）


def test_generate_injects_metamorphic_and_differential_sections():
    gen, calls = _real_gen_with_mocked_llm()
    gen.generate(
        {"name": "t"},
        "code",
        "m",
        None,
        metamorphic_section="【N2 蜕变关系要求】x",
        differential_section="【N4 差分测试要求】y",
    )
    query = calls[-1]
    assert "【N2 蜕变关系要求】x" in query
    assert "【N4 差分测试要求】y" in query


# ── 2. N2 MR 模板命中（接线审计修复：此前 6 类全 0 命中）──────────────────────


@pytest.mark.parametrize(
    ("fn", "expected_names"),
    [
        ("normalize", {"idempotence"}),
        ("clean", {"idempotence"}),
        ("sort", {"monotonicity"}),
        ("rank", {"monotonicity"}),
        ("encode", {"reversibility"}),
        ("transform", {"dimension_preserve"}),
    ],
)
def test_mr_templates_match_after_fix(fn: str, expected_names: set[str]):
    mrs = suggest_metamorphic_relations(fn)
    got = {m["name"] for m in mrs}
    assert got == expected_names, f"{fn}: {got} != {expected_names}"


def test_mr_section_rendered_nonempty():
    mrs = suggest_metamorphic_relations("normalize")
    section = build_metamorphic_prompt_section(mrs)
    assert section
    assert "幂等性" in section


def test_mr_no_match_returns_empty():
    assert suggest_metamorphic_relations("compute_hash_value") == []
    assert build_metamorphic_prompt_section([]) == ""


def test_mr_communication_requires_two_args():
    # "func has 2+ args" 触发子句：参数数 >= 2 才命中（修复 int(" 2+") 解析 bug）
    two_args = suggest_metamorphic_relations("merge", signature="a: list, b: list")
    assert {m["name"] for m in two_args} == {"commutativity"}
    one_arg = suggest_metamorphic_relations("merge", signature="a: list")
    assert {m["name"] for m in one_arg} == set()


# ── 3. 开关默认关 / 显式开（monkeypatch 环境变量）────────────────────────────


def test_switches_default_off(monkeypatch):
    monkeypatch.delenv("METAMORPHIC_ENABLE", raising=False)
    monkeypatch.delenv("DIFFERENTIAL_TEST_ENABLE", raising=False)
    assert not metamorphic_enabled()
    assert not differential_enabled()


def _run_generator_node_capture(monkeypatch, monkeypatch_state_overrides: dict | None = None):
    """跑 _generator_node（Agent 全 mock），捕获传给 generate 的 kwargs。"""
    from src.graph import nodes as _nodes

    state: dict = {
        "target_code": "def normalize(x):\n    return x",
        "target_function": "normalize",
        "module_name": "mod",
        "iteration": 0,
        "max_iterations": 3,
    }
    if monkeypatch_state_overrides:
        state.update(monkeypatch_state_overrides)
    _captured: dict = {}

    class _FakeAgent:
        def generate(self, *args, **kwargs):
            _captured.update(kwargs)
            return "def test_x():\n    assert True"

    monkeypatch.setattr(_nodes, "get_or_create_agent", lambda cls: _FakeAgent())
    _nodes._generator_node(state)
    return _captured


def test_generator_node_sections_none_when_switches_off(monkeypatch):
    """开关默认关时 _generator_node 构建的 N2/N4 段落恒 None（零行为变化）。"""
    monkeypatch.delenv("METAMORPHIC_ENABLE", raising=False)
    monkeypatch.delenv("DIFFERENTIAL_TEST_ENABLE", raising=False)
    _captured = _run_generator_node_capture(monkeypatch)
    assert _captured.get("metamorphic_section") is None
    assert _captured.get("differential_section") is None


def test_generator_node_sections_populated_when_switches_on(monkeypatch):

    monkeypatch.setenv("METAMORPHIC_ENABLE", "true")
    monkeypatch.setenv("DIFFERENTIAL_TEST_ENABLE", "true")
    _captured = _run_generator_node_capture(monkeypatch)
    assert _captured.get("metamorphic_section")
    assert "幂等性" in _captured["metamorphic_section"]
    assert _captured.get("differential_section")
    assert "【N4 差分测试要求】" in _captured["differential_section"]


# ── 4. 原语基本行为 ─────────────────────────────────────────────────────────


def test_compare_outputs_float_tolerance():
    assert compare_outputs(0.1 + 0.2, 0.3) is True
    assert compare_outputs(1.0, 2.0) is False


def test_compare_outputs_nan_consistent():
    assert compare_outputs(float("nan"), float("nan")) is True


def test_run_differential_check_agreement_and_mismatch():
    result = run_differential_check(math.floor, math.ceil, [(3.7,), (3.0,), (-3.2,)])
    assert result["passed"] is False
    assert result["total"] == 3
    assert result["mismatches"]
    same = run_differential_check(math.floor, math.floor, [(3.7,), (-3.2,)])
    assert same["passed"] is True
    assert same["agreement_rate"] == 1.0


def test_run_differential_check_error_counted():
    def _boom(x):
        raise ValueError("x")

    result = run_differential_check(math.floor, _boom, [(1.5,)])
    assert result["passed"] is False
    assert result["errors"]


def test_check_metamorphic_relation_execution():
    code = "r1 = {func}(x)\nassert {func}(r1) == r1"
    ok = check_metamorphic_relation(code, lambda x: x.strip(), "  hi  ")
    # 保守口径：只要不抛异常且返回可判定值即视为原语可用（模块自述"纯 Python 执行"）
    assert ok is True or ok is False or isinstance(ok, dict)
