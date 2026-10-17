#!/usr/bin/env python3
"""N 轮：逻辑/规约链路探针模块（`scripts/tools/e2e_probes_logic.py`）的回归锁定。

覆盖两类内容：
1. **契约**：探针注册信息（名称唯一、group=logic、仅 1 个 requires_llm=true、
   timeout 合理）——防止"探针没注册/被误标 LLM"导致功能矩阵静默缺口；
2. **探针真实行为**（零 LLM 探针直接执行）：SpecIR 解析 / 白名单 / 确定性 oracle
   编译 / SMT 见证 / spec_anchor 接线（N-3）/ 独立判读字段（N-3）/ 停滞开关 /
   mutation advisor 装配 / branch 覆盖测量全部 pass；
3. **负控（探针的探针）**：monkeypatch 关键依赖制造"静默失效"（解析恒 None、
   oracle 产物恒空、白名单恒拒绝、开关失效），断言探针返回 fail 而非 pass——
   保证探针本身不会"永远绿"。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logic = importlib.import_module("scripts.tools.e2e_probes_logic")


class TestRegistrationContract:
    def test_probes_registered_with_unique_names(self):
        names = [p.name for p in logic.PROBES]
        assert len(names) == len(set(names)), f"探针名重复：{names}"
        assert len(logic.PROBES) >= 12

    def test_all_in_logic_group(self):
        assert {p.group for p in logic.PROBES} == {"logic"}

    def test_exactly_one_llm_probe(self):
        llm = [p for p in logic.PROBES if p.requires_llm]
        assert len(llm) == 1, f"LLM 探针应恰为 1 个（logic 档最小任务）：{[p.name for p in llm]}"

    def test_timeouts_are_bounded(self):
        for probe in logic.PROBES:
            assert 10 <= probe.timeout_s <= 600, f"{probe.name} timeout 越界：{probe.timeout_s}"

    def test_names_prefixed(self):
        for probe in logic.PROBES:
            assert probe.name.startswith("logic-"), f"{probe.name} 未按组前缀命名"


class TestZeroLlmProbesPass:
    """零 LLM 探针在当前代码上必须全部 pass（skip 仅允许可选依赖缺失）。"""

    @pytest.mark.parametrize(
        "probe_name",
        [
            "logic-spec-ir-parse",
            "logic-spec-expr-whitelist",
            "logic-spec-oracle-compile",
            "logic-smt-witness",
            "logic-spec-anchor-oracle-wiring",
            "logic-oracle-independent-judging",
            "logic-stagnation-switch",
            "logic-mutation-advisor-assembly",
            "logic-branch-coverage-inject",
            "logic-oracle-instrument-safety",
            "logic-oracle-replay-instrument-breakdown",
            "logic-oracle-precondition-input-filter",
        ],
    )
    def test_probe_passes(self, probe_name):
        probe = next(p for p in logic.PROBES if p.name == probe_name)
        outcome = probe.func()
        assert outcome.status in ("pass", "skip"), f"{probe_name}: {outcome.status} — {outcome.detail}"
        if outcome.status == "skip":
            assert outcome.detail.strip(), "skip 必须带原因"


class TestOracleInstrumentProbesNegativeControls:
    """O-1 探针必须能识别"仪器回退"（打坏后 fail/skip 而非静默 pass）。"""

    def test_precondition_filter_detects_unguarded_binding(self, monkeypatch):
        from src.specs import spec_ir_v2

        # 模拟加固回退：产物直接绑定首个（违反前件的）候选、无 skip harness
        monkeypatch.setattr(
            spec_ir_v2,
            "compile_spec_oracle",
            lambda *a, **k: "def test_specir_v2_oracle():\n    side = 0\n    assert side == 0\n",
        )
        outcome = logic.probe_oracle_precondition_input_filter()
        assert outcome.status == "fail"
        assert "未生效" in outcome.detail

    def test_replay_breakdown_skips_without_artifact(self, monkeypatch, tmp_path):
        fresh_root = tmp_path / "no_such_root"
        real_path = logic.__file__
        # 让探针解析到不存在的结果目录 → 应 skip（带原因），而不是 fail/静默 pass
        monkeypatch.setattr(logic, "__file__", str(fresh_root / "scripts" / "tools" / "e2e_probes_logic.py"))
        outcome = logic.probe_oracle_replay_instrument_breakdown()
        assert outcome.status == "skip"
        assert outcome.detail.strip()
        assert real_path  # 保留原路径引用（防未使用告警）


class TestNegativeControls:
    """探针必须能识别"静默失效"——把依赖打坏后探针要 fail，而不是继续 pass。"""

    def test_spec_ir_parse_detects_none(self, monkeypatch):
        from src.specs import spec_ir

        monkeypatch.setattr(spec_ir, "parse_logic_analysis", lambda *a, **k: None)
        outcome = logic.probe_spec_ir_parse()
        assert outcome.status == "fail"
        assert "返回 None" in outcome.detail

    def test_spec_oracle_compile_detects_empty(self, monkeypatch):
        from src.specs import spec_ir_v2

        monkeypatch.setattr(spec_ir_v2, "compile_spec_oracle", lambda *a, **k: "")
        outcome = logic.probe_spec_oracle_compile()
        assert outcome.status == "fail"
        assert "空串" in outcome.detail

    def test_whitelist_detects_accepting_dangerous(self, monkeypatch):
        from src.specs import spec_ir_v2

        monkeypatch.setattr(spec_ir_v2, "clause_reject_reason", lambda *a, **k: None)
        outcome = logic.probe_spec_expr_whitelist()
        assert outcome.status == "fail"
        assert "危险子句" in outcome.detail

    def test_smt_detects_empty_witnesses(self, monkeypatch):
        from src.specs import spec_smt

        monkeypatch.setattr(spec_smt, "smt_available", lambda: True)
        monkeypatch.setattr(spec_smt, "generate_spec_witnesses", lambda *a, **k: [])
        outcome = logic.probe_smt_witness()
        assert outcome.status == "fail"
        assert "未产出见证" in outcome.detail

    def test_stagnation_detects_broken_switch(self, monkeypatch):
        from src.graph import workflow

        monkeypatch.setattr(workflow, "_coverage_stall_enabled", lambda: False)
        outcome = logic.probe_stagnation_switch()
        assert outcome.status == "fail"
        assert "不生效" in outcome.detail

    def test_mutation_advisor_detects_missing_node(self, monkeypatch):
        from src.graph import workflow

        class _FakeGraph:
            def __init__(self) -> None:
                self.nodes: dict = {}

        monkeypatch.setattr(workflow, "build_workflow", lambda **k: _FakeGraph())
        outcome = logic.probe_mutation_advisor_assembly()
        assert outcome.status == "fail"
        assert "未装配" in outcome.detail

    def test_branch_coverage_detects_none(self, monkeypatch):
        from src.tools import branch_coverage_inject

        monkeypatch.setattr(branch_coverage_inject, "measure_branch_coverage", lambda *a, **k: None)
        outcome = logic.probe_branch_coverage_inject()
        assert outcome.status == "fail"
        assert "返回 None" in outcome.detail

    def test_wiring_detects_not_attempted(self, monkeypatch):
        from src.graph import nodes

        monkeypatch.setattr(
            nodes,
            "_append_spec_oracle_to_test_with_verdict",
            lambda *a, **k: ("code", False, nodes._SPEC_ORACLE_VERDICT_NOT_ATTEMPTED),
        )
        outcome = logic.probe_spec_anchor_oracle_wiring()
        assert outcome.status == "fail"
        assert "not_attempted" in outcome.detail
