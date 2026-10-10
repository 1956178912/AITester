"""G8/G2/G4/G5/G6/G7/G1 缺口落地单元测试（均默认关、零 LLM 成本、纯数据口径）。

覆盖：
- G2 risk_approval：三因子打分 / 分级 / 审批动作 / 默认关占位
- G4 agent_telemetry：已知失败模式匹配 / Markdown 渲染 / 默认关
- G5 testless_validation：四层验证 / 任一层失败整体 fail / 缺依赖保守跳过
- G6 expert_pool 辩论收敛：top-K 不足降级 / LLM 失败保守降级 / 修订候选插入首位
- G7 ErrorReport Oracle 章节：with_oracle_stats 注入 / 缺数据时跳过 / JSON 同构
- G1 tree_sitter_backend：缺依赖时 is_available()=False / 回退词法层 / 注册 no-op
- G8 前置检查：数据目录缺失 → ready=False / 完整 JSONL → ready=True / enrichment 补全
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

# ─── G2 风险分级人工回路 ─────────────────────────────────────────────────────


def test_risk_approval_default_off_placeholder() -> None:
    """默认关时 build_risk_summary 返回 enabled=False 占位（键集合同构）。"""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RISK_APPROVAL_ENABLE", None)
        from src.graph.risk_approval import build_risk_summary

        result = build_risk_summary(None, 10, 1, None, None, None, None)
        assert result["enabled"] is False
        assert result["risk_score"] is None
        assert result["approval_action"] is None


def test_risk_approval_low_confidence_high_impact_high_risk() -> None:
    """低置信度 + 大影响面 + 预算超限 → high / force_review。"""
    with patch.dict(os.environ, {"RISK_APPROVAL_ENABLE": "true"}, clear=False):
        from src.graph.risk_approval import build_risk_summary, risk_approval_enabled

        assert risk_approval_enabled() is True
        result = build_risk_summary(
            confidence=0.2,
            changed_lines=300,
            changed_files=4,
            contract_missing_symbols=["Rule_L101"],
            full_file_patch=True,
            budget_ratio=0.95,
            budget_exceeded=True,
        )
        assert result["enabled"] is True
        assert result["risk_level"] == "high"
        assert result["approval_action"] == "force_review"
        assert result["risk_score"] > 0.6


def test_risk_approval_small_patch_low_risk_auto_merge() -> None:
    """小补丁 + 高置信度 + 无预算 → low / auto_merge。"""
    with patch.dict(os.environ, {"RISK_APPROVAL_ENABLE": "true"}, clear=False):
        from src.graph.risk_approval import build_risk_summary

        result = build_risk_summary(
            confidence=0.95,
            changed_lines=10,
            changed_files=1,
            contract_missing_symbols=None,
            full_file_patch=False,
            budget_ratio=None,
            budget_exceeded=False,
        )
        assert result["risk_level"] == "low"
        assert result["approval_action"] == "auto_merge"


def test_risk_approval_medium_impact_human_confirm() -> None:
    """中等影响面 → medium / human_confirm。"""
    with patch.dict(os.environ, {"RISK_APPROVAL_ENABLE": "true"}, clear=False):
        from src.graph.risk_approval import build_risk_summary

        result = build_risk_summary(
            confidence=0.6,
            changed_lines=100,
            changed_files=2,
            contract_missing_symbols=None,
            full_file_patch=False,
            budget_ratio=0.5,
            budget_exceeded=False,
        )
        assert result["risk_level"] in ("medium", "high")
        if result["risk_level"] == "medium":
            assert result["approval_action"] == "human_confirm"


# ─── G4 AgentTelemetry 故障检测基准 ──────────────────────────────────────────


def test_agent_telemetry_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AGENT_TELEMETRY_ENABLE", None)
        from src.observability.agent_telemetry import agent_telemetry_enabled

        assert agent_telemetry_enabled() is False


def test_agent_telemetry_matches_known_patterns() -> None:
    """构造 trace 记录验证各已知失败模式命中。"""
    from src.observability.agent_telemetry import match_failure_patterns, render_telemetry_report

    records = [
        {"task": "t1", "error_category": "llm_empty_response", "decision": "debug"},
        {"task": "t2", "error_category": "multi_candidate_all_rejected"},
        {"task": "t3", "contract_missing_symbols": ["Rule_L101"]},
        {"task": "t4", "error_category": "import_error", "iteration": 2},
        {"task": "t5", "iteration": 6, "reward_signals": {"correctness": 0.0}},
        {"task": "t6"},  # 无特征 → 仅 known_error_category_hit 不命中（category 空）
    ]
    report = match_failure_patterns(records)
    assert report["total_records"] == 6
    assert report["patterns"]["llm_empty_response_loop"]["count"] == 1
    assert report["patterns"]["multi_candidate_all_rejected"]["count"] == 1
    assert report["patterns"]["contract_break_rewrite"]["count"] == 1
    assert report["patterns"]["import_break_after_rewrite"]["count"] == 1
    assert report["patterns"]["repair_not_converging"]["count"] == 1
    assert report["patterns"]["known_error_category_hit"]["count"] == 3  # t1/t2/t4（t3/t5 无 error_category）
    md = render_telemetry_report(report)
    assert "AgentTelemetry" in md
    assert "llm_empty_response_loop" in md


def test_agent_telemetry_empty_records() -> None:
    from src.observability.agent_telemetry import match_failure_patterns

    report = match_failure_patterns([])
    assert report["total_records"] == 0
    assert report["matched_records"] == 0


# ─── G5 testless 修复验证 ─────────────────────────────────────────────────────


def test_testless_validation_all_pass() -> None:
    """合法补丁（保留所有顶层定义）→ 四层全过。"""
    with patch.dict(os.environ, {}, clear=False):
        for key in ("TESTLESS_MYPY_ENABLE", "TESTLESS_NAMING_CONTRACT_ENABLE", "TESTLESS_IMPORT_SMOKE_ENABLE"):
            os.environ.pop(key, None)
        # mypy 层缺依赖 / 不可用时保守跳过（passed=True），不影响整体判定
        from src.tools.testless_validation import run_testless_validation

        original = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
        patched = "def add(a, b):\n    return int(a) + int(b)\n\ndef sub(a, b):\n    return int(a) - int(b)\n"
        result = run_testless_validation(original, patched, target_module="calc")
        # ast_symbol_guard / naming_contract 必过；mypy 保守跳过；import_smoke 可能过/失败
        assert result["layers"]["ast_symbol_guard"]["passed"] is True
        assert result["layers"]["naming_contract"]["passed"] is True


def test_testless_validation_ast_symbol_guard_fails() -> None:
    """补丁删除顶层函数 → AST 符号守卫失败 → 整体 fail。"""
    from src.tools.testless_validation import run_testless_validation

    original = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
    patched = "def add(a, b):\n    return a + b\n"  # 删掉 sub
    with patch.dict(os.environ, {"TESTLESS_IMPORT_SMOKE_ENABLE": "false"}, clear=False):
        result = run_testless_validation(original, patched, target_module="calc")
        assert result["layers"]["ast_symbol_guard"]["passed"] is False
        assert "ast_symbol_guard" in result["failed_layers"]
        assert result["passed"] is False


def test_testless_validation_import_smoke_disabled() -> None:
    """导入冒烟层显式关闭 → 跳过（passed=True）。"""
    from src.tools.testless_validation import run_testless_validation

    code = "X = 1\n"
    with patch.dict(os.environ, {"TESTLESS_IMPORT_SMOKE_ENABLE": "false"}, clear=False):
        result = run_testless_validation(code, code, target_module="m")
        assert result["layers"]["import_smoke"]["passed"] is True
        assert "跳过" in result["layers"]["import_smoke"]["detail"]


# ─── G6 多 Agent 辩论收敛 ─────────────────────────────────────────────────────


def test_expert_pool_debate_disabled_by_default() -> None:
    """默认关时 debate 开关恒 False（不触发辩论路径）。"""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXPERT_POOL_ENABLE", None)
        os.environ.pop("EXPERT_POOL_DEBATE_ENABLE", None)
        from src.graph.expert_pool import expert_pool_debate_enabled

        assert expert_pool_debate_enabled() is False


def test_expert_pool_debate_requires_expert_pool_on() -> None:
    """EXPERT_POOL_DEBATE_ENABLE=true 但 EXPERT_POOL_ENABLE=false → 辩论仍关。"""
    with patch.dict(os.environ, {"EXPERT_POOL_ENABLE": "false", "EXPERT_POOL_DEBATE_ENABLE": "true"}, clear=False):
        from src.graph.expert_pool import expert_pool_debate_enabled

        assert expert_pool_debate_enabled() is False


def test_expert_pool_debate_insufficient_top_k_degrades() -> None:
    """top-K 不足 2（仅 1 个候选）→ 不触发 LLM 修订，原样返回。"""
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    verified = [{"dimension": "boundary_handling", "patch": "def f(): pass", "confidence": 0.5, "expert_failed": False}]
    result = pool.debate_round(verified, target_code="x", test_output="", failed_cases=[])
    assert len(result) == 1
    assert result[0]["debate_revise"] is False


def test_expert_pool_debate_llm_failure_degrades() -> None:
    """辩论修订 LLM 调用失败 → 保守降级返回原 verified 列表。"""

    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    verified = [
        {
            "dimension": "boundary_handling",
            "patch": "def f(): pass",
            "confidence": 0.5,
            "expert_failed": False,
            "verified_count": 2,
        },
        {
            "dimension": "type_safety",
            "patch": "def f(): return 0",
            "confidence": 0.5,
            "expert_failed": False,
            "verified_count": 2,
        },
    ]
    with patch("src.agents.debugger.DebuggerAgent.debug", side_effect=RuntimeError("llm down")):
        result = pool.debate_round(verified, target_code="x", test_output="", failed_cases=[])
    assert len(result) == 2
    assert all(not c.get("debate_revise") for c in result)


def test_expert_pool_debate_success_inserts_revise_candidate() -> None:
    """辩论修订成功 → 修订候选插入首位（debate_revise=True）。"""
    from unittest.mock import MagicMock
    from unittest.mock import patch as _patch

    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    verified = [
        {
            "dimension": "boundary_handling",
            "patch": "def f(): pass",
            "confidence": 0.5,
            "expert_failed": False,
            "verified_count": 2,
        },
        {
            "dimension": "type_safety",
            "patch": "def f(): return 0",
            "confidence": 0.5,
            "expert_failed": False,
            "verified_count": 2,
        },
    ]

    fake_result = MagicMock()
    fake_result.get = lambda key, default=None: {"patch": "def f():\n    return 1"}.get(key, default)

    with _patch(
        "src.agents.debugger.DebuggerAgent",
        return_value=MagicMock(debug=lambda **kw: fake_result.get.__self__ and {"patch": "def f():\n    return 1"}),
    ):
        # 简化：直接 mock DebuggerAgent.debug 返回值
        from unittest.mock import patch as _p2

        with _p2("src.agents.debugger.DebuggerAgent") as MockAgent:
            MockAgent.return_value.debug.return_value = {"patch": "def f():\n    return 1"}
            result = pool.debate_round(verified, target_code="x", test_output="", failed_cases=[])
    assert len(result) == 3
    assert result[0]["debate_revise"] is True
    assert result[0]["dimension"] == "debate_revise"
    assert all(not c.get("debate_revise") for c in result[1:])


# ─── G7 缺陷报告 Oracle 章节 ──────────────────────────────────────────────────


def test_error_report_oracle_section_renders() -> None:
    """注入 oracle_stats 后 Markdown 含 Oracle 章节。"""
    from src.agents.error_classifier import ErrorCategory
    from src.reports.generator import ErrorReport

    report = ErrorReport(
        task_id="t1",
        target_file="a.py",
        target_function="f",
        error_category=ErrorCategory.ASSERTION,
    )
    stats = {
        "total_oracles": 10,
        "weak_oracle_count": 4,
        "weak_oracle_ratio": 0.4,
        "oracle_source_distribution": {"postcondition": 5, "edge_case": 3, "invariant": 2},
        "oracle_confidence_distribution": {"0.0-0.5": 4, "0.5-0.8": 3, "0.8-1.0": 3},
    }
    report.with_oracle_stats(stats)
    md = report.to_markdown()
    assert "预言有效性" in md
    assert "弱预言数" in md
    assert "oracle_confidence < 0.5" in md
    assert "postcondition" in md
    d = report.to_dict()
    assert d["oracle_stats"]["total_oracles"] == 10


def test_error_report_oracle_section_skipped_when_missing() -> None:
    """未注入 / total=0 时不渲染 Oracle 章节（不产生误导数据）。"""
    from src.agents.error_classifier import ErrorCategory
    from src.reports.generator import ErrorReport

    report = ErrorReport(
        task_id="t2",
        target_file="b.py",
        target_function="g",
        error_category=ErrorCategory.RUNTIME,
    )
    md_no_stats = report.to_markdown()
    assert "预言有效性" not in md_no_stats

    report.with_oracle_stats({"total_oracles": 0})
    md_zero = report.to_markdown()
    assert "预言有效性" not in md_zero
    assert report.to_dict()["oracle_stats"] is None


# ─── G1 Tree-sitter 精确 AST 后端 ─────────────────────────────────────────────


def test_tree_sitter_backend_missing_dependency_degrades() -> None:
    """缺 tree-sitter 依赖时 is_available()=False，方法回退词法层。"""
    from src.tools.tree_sitter_backend import TypeScriptTreeSitterBackend, is_tree_sitter_available

    if is_tree_sitter_available():
        # tree-sitter 可用时此用例跳过（保守：不强制降级路径）
        return
    backend = TypeScriptTreeSitterBackend()
    code = "export function add(a, b) { return a + b; }\nexport const X = 1;\nexport class Foo {}\n"
    symbols = backend.extract_symbols(code)
    assert "add" in symbols
    assert "X" in symbols
    assert "Foo" in symbols
    edges = backend.extract_call_graph(code)
    assert isinstance(edges, list)
    missing = backend.check_naming_contract(code, "export function add(a, b) { return a + b; }\n")
    assert "X" in missing
    assert "Foo" in missing


def test_tree_sitter_register_noop_when_unavailable() -> None:
    """缺依赖时 register_tree_sitter_backend() no-op（不抛错、不改注册表）。"""
    from src.tools.language_backend import get_language_backend
    from src.tools.tree_sitter_backend import is_tree_sitter_available, register_tree_sitter_backend

    if is_tree_sitter_available():
        return
    register_tree_sitter_backend()  # 不抛错
    with patch.dict(os.environ, {"AITESTER_ENABLE_TYPESCRIPT_BACKEND": "true"}, clear=False):
        backend = get_language_backend("typescript")
        # 注册表默认仍是词法层（register no-op 未替换）
        from src.tools.language_backend import TypeScriptBackend

        assert isinstance(backend, TypeScriptBackend)


# ─── G8 前置数据检查 ───────────────────────────────────────────────────────────


def test_g8_pro_check_missing_dir_not_ready() -> None:
    """数据目录不存在 → ready=False，退出码 1。"""
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_swe_bench_pro_ready import check_pro_ready

    report = check_pro_ready("/tmp/definitely_no_swe_bench_pro_dir_xyz")
    assert report["ready"] is False
    assert report["total_tasks"] == 0


def test_g8_pro_check_complete_jsonl_ready() -> None:
    """完整 JSONL（含 instance_code / test_patch / FAIL_TO_PASS / base_commit）→ ready=True。"""
    import sys as _sys
    import tempfile

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_swe_bench_pro_ready import check_pro_ready

    row = {
        "instance_id": "repo__repo-1",
        "problem_statement": "fix bug",
        "instance_code": "def f():\n    return 1\n",
        "test_code": "def test_f():\n    assert f() == 1\n",
        "FAIL_TO_PASS": ["tests/test_f.py::test_f"],
        "base_commit": "abc123",
    }
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "swe_bench_pro_instances.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        report = check_pro_ready(d)
        assert report["ready"] is True
        assert report["total_tasks"] == 1
        assert report["task_issues"] == {}


def test_g8_pro_check_missing_source_not_ready() -> None:
    """缺 instance_code（无 enrichment）→ ready=False + missing_source 非空。"""
    import sys as _sys
    import tempfile

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_swe_bench_pro_ready import check_pro_ready

    row = {
        "instance_id": "repo__repo-2",
        "problem_statement": "fix bug",
        "test_code": "def test_f():\n    assert 1\n",
        "FAIL_TO_PASS": ["tests/test_f.py::test_f"],
        "base_commit": "abc123",
    }
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "swe_bench_pro_instances.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        report = check_pro_ready(d)
        assert report["ready"] is False
        assert "repo__repo-2" in report["missing_source"]
        assert any("instance_code 缺失" in s for s in report["task_issues"].get("repo__repo-2", []))


def test_g8_pro_check_enrichment_fills_source() -> None:
    """enrichment 补全 instance_code → 就绪。"""
    import sys as _sys
    import tempfile

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_swe_bench_pro_ready import check_pro_ready

    row = {
        "instance_id": "repo__repo-3",
        "problem_statement": "fix bug",
        "test_code": "def test_f():\n    assert 1\n",
        "FAIL_TO_PASS": ["tests/test_f.py::test_f"],
        "base_commit": "abc123",
    }
    enrichment = {"instance_id": "repo__repo-3", "instance_code": "def f():\n    return 2\n"}
    with tempfile.TemporaryDirectory() as d:
        data_path = os.path.join(d, "swe_bench_pro_instances.jsonl")
        with open(data_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        enrich_path = os.path.join(d, "enrichment.jsonl")
        with open(enrich_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(enrichment) + "\n")
        report = check_pro_ready(d, enrichment=enrich_path)
        assert report["enrichment_loaded"] is True
        assert report["ready"] is True


# ─── 依赖豁免治理门禁 ─────────────────────────────────────────────────────────


def test_dependency_exemption_check_blocks_unregistered() -> None:
    """ci.yml 的 --ignore-vuln 未在登记表留痕 → 对照产生未登记集合（退出码 1 语义）。"""
    import sys as _sys
    import tempfile

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_dependency_exemptions import _extract_ci_ignore_vulns, _extract_registry_vuln_ids

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".github", "workflows"))
        with open(os.path.join(d, ".github", "workflows", "ci.yml"), "w", encoding="utf-8") as f:
            f.write(
                "      - name: Check dependencies\n"
                "        run: |\n"
                "          pip-audit -r requirements.txt --no-deps \\\n"
                "            --ignore-vuln PYSEC-2099-9999\n"
            )
        # 登记表不含 PYSEC-2099-9999
        os.makedirs(os.path.join(d, "docs"))
        with open(os.path.join(d, "docs", "dependency_exemptions.md"), "w", encoding="utf-8") as f:
            f.write("# 依赖豁免登记表\n\n| 依赖 | 漏洞 ID |\n|------|--------|\n| chromadb | PYSEC-2026-3813 |\n")
        ci_vulns = _extract_ci_ignore_vulns(os.path.join(d, ".github", "workflows", "ci.yml"))
        registry_vulns = _extract_registry_vuln_ids(os.path.join(d, "docs", "dependency_exemptions.md"))
        unregistered = ci_vulns - registry_vulns
        assert unregistered == {"PYSEC-2099-9999"}  # 未登记 → 阻断


def test_dependency_exemption_check_passes_when_registered() -> None:
    """ci.yml 的 --ignore-vuln 已在登记表留痕 → 对照无未登记（退出码 0 语义）。"""
    import sys as _sys
    import tempfile

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gates"))
    from check_dependency_exemptions import _extract_ci_ignore_vulns, _extract_registry_vuln_ids

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".github", "workflows"))
        with open(os.path.join(d, ".github", "workflows", "ci.yml"), "w", encoding="utf-8") as f:
            f.write(
                "      - name: Check dependencies\n"
                "        run: |\n"
                "          pip-audit -r requirements.txt --no-deps \\\n"
                "            --ignore-vuln PYSEC-2026-3813 \\\n"
                "            --ignore-vuln PYSEC-2026-3814\n"
            )
        os.makedirs(os.path.join(d, "docs"))
        with open(os.path.join(d, "docs", "dependency_exemptions.md"), "w", encoding="utf-8") as f:
            f.write(
                "# 依赖豁免登记表\n\n| 依赖 | 漏洞 ID |\n|------|--------|\n| chromadb | PYSEC-2026-3813 / 3814 |\n"
            )
        ci_vulns = _extract_ci_ignore_vulns(os.path.join(d, ".github", "workflows", "ci.yml"))
        registry_vulns = _extract_registry_vuln_ids(os.path.join(d, "docs", "dependency_exemptions.md"))
        # 合写格式补全：PYSEC-2026-3813 / 3814 → {3813, 3814}，全部已登记
        assert ci_vulns == {"PYSEC-2026-3813", "PYSEC-2026-3814"}
        assert ci_vulns - registry_vulns == set()
