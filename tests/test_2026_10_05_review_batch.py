"""
2026-10-05 审查优化批次测试（R1a/R1b/R1c/R4b/R11/R15/R16/R17）。

覆盖本批次落地的核心改动：
- R1a：spec_ir v1 编译缺陷修复（分号 join 语法错误 / assert True 恒真断言）；
- R1b/R6：spec_ir_v2 签名感知绑定（compile_spec_oracle + extract_signature_params）；
- R1c：确定性规约 oracle 执行接线（_append_spec_oracle_to_test + SPEC_ORACLE_EXEC_ENABLE）；
- R4b：patch_rollback fail-closed 口径开关（PATCH_ROLLBACK_FAIL_CLOSED）；
- R11：run_benchmark 确定性采样级联（_apply_deterministic_temperature）；
- R15：AITESTER_PROFILE 开关预设（_apply_profile_presets）；
- R16：rogue_monitor 接线（ROGUE_MONITOR_ENABLE + base_agent 上报）；
- R17：_should_debug / determine_stop_reason 结构化路由信号（ROUTE_STRUCTURED_ENABLE）。
"""

import ast
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.specs.spec_ir import compile_to_hypothesis, extract_signature_params
from src.specs.spec_ir_v2 import compile_spec_oracle
from src.tools.patch_rollback import PatchRollbackProtocol, run_p2p_regression

# ─── R1a：v1 编译缺陷修复 ────────────────────────────────────────────────────


class TestCompileToHypothesisFix:
    """R1a：分号 join 语法错误与 assert True 恒真断言的修复口径。"""

    def test_multi_boundary_parametrize_is_valid_python(self):
        """≥2 条边界时产物必须是合法 Python（历史 bug：`'; '.join` 产 SyntaxError）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "inc",
            "preconditions": [],
            "postconditions": [],
            "invariants": [],
            "boundaries": [
                {"input": 1, "expected": 2, "rationale": ""},
                {"input": 4, "expected": 5, "rationale": ""},
            ],
            "oracle_kind": "boundary",
        }
        code = compile_to_hypothesis(spec, target_module="m", target_function="inc")
        assert code, "有边界材料时应产出编译产物"
        # 产物必须可被 ast.parse（历史分号 join 产物在此抛 SyntaxError）
        ast.parse(code)
        # 逗号分隔（而非分号）的参数化列表
        assert "(1, 2), (4, 5)" in code
        assert ";" not in code

    def test_invariants_no_tautological_assert(self):
        """NL 不变量不再编译为 assert True 恒真断言（假通过通道封堵）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "inc",
            "preconditions": [],
            "postconditions": [],
            "invariants": ["输出恒为正整数"],
            "boundaries": [{"input": 1, "expected": 2, "rationale": ""}],
            "oracle_kind": "boundary",
        }
        code = compile_to_hypothesis(spec, target_module="m", target_function="inc")
        assert "assert True" not in code, "不得产出恒真断言"
        assert "@given" not in code, "NL 不变量不再生成 hypothesis 测试函数"
        # NL 原文保留为溯源注释
        assert "# invariant" in code

    def test_no_boundaries_returns_empty(self):
        """无边界材料时返回空串（不产出无断言的空测试文件）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "inc",
            "preconditions": [],
            "postconditions": ["r > 0"],
            "invariants": ["r 非负"],
            "boundaries": [],
            "oracle_kind": "postcondition",
        }
        assert compile_to_hypothesis(spec, target_module="m", target_function="inc") == ""

    def test_missing_module_or_function_returns_empty(self):
        """缺模块名 / 函数名时保守返回空串。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "inc",
            "boundaries": [{"input": 1, "expected": 2}],
        }
        assert compile_to_hypothesis(spec, target_module="", target_function="inc") == ""
        assert compile_to_hypothesis(None, target_module="m", target_function="inc") == ""


# ─── R1b：签名提取与签名感知绑定 ─────────────────────────────────────────────


class TestExtractSignatureParams:
    """R1b：extract_signature_params 的 AST 签名提取口径。"""

    def test_single_param(self):
        """单参数函数提取参数名。"""
        src = "def double(x):\n    return x * 2\n"
        assert extract_signature_params(src, "double") == ["x"]

    def test_multi_and_kwonly_params(self):
        """多参数 + 仅关键字参数全部提取；*args/**kwargs 排除。"""
        src = "def f(a, b, *, flag, **kw):\n    return a\n"
        assert extract_signature_params(src, "f") == ["a", "b", "flag"]

    def test_self_excluded(self):
        """方法首参 self 不作为规约绑定变量。"""
        src = "class C:\n    def m(self, value):\n        return value\n"
        assert extract_signature_params(src, "m") == ["value"]

    def test_function_not_found_or_bad_source(self):
        """函数不存在 / 源码语法错误 → None（与 0 参的 [] 显式区分，调用方降级）。"""
        assert extract_signature_params("def g():\n    pass\n", "f") is None
        assert extract_signature_params("def broken(:\n", "broken") is None
        assert extract_signature_params("", "f") is None
        assert extract_signature_params("def f(x):\n    pass\n", "") is None

    def test_zero_param_returns_empty_list(self):
        """0 参函数返回 []（签名已知），与"未找到"的 None 区分。"""
        assert extract_signature_params("def f():\n    return 42\n", "f") == []


class TestCompileSpecOracleSignatureAware:
    """R1b：compile_spec_oracle 的签名感知绑定（R6 修复：解除 {r,x,a,b,y} 限制）。"""

    def test_custom_param_names_compilable(self):
        """自定义参数名的后置条件可编译（历史口径下必然不可编译）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "add",
            "preconditions": [],
            "postconditions": ["r == first + second"],
            "invariants": [],
            "boundaries": [{"input": (1, 2), "expected": 3, "rationale": ""}],
            "oracle_kind": "postcondition",
        }
        code = compile_spec_oracle(spec, "m", "add", signature_params=["first", "second"])
        assert code, "签名感知下自定义参数名子句应可编译"
        assert "r == first + second" in code
        ast.parse(code)

    def test_single_param_call_arity_fixed(self):
        """单参函数按签名调用（历史口径误产 func(a, b) 触发 TypeError）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "double",
            "preconditions": [],
            "postconditions": ["r == value * 2"],
            "invariants": [],
            "boundaries": [{"input": 3, "expected": 6, "rationale": ""}],
            "oracle_kind": "postcondition",
        }
        code = compile_spec_oracle(spec, "m", "double", signature_params=["value"])
        assert "double(value)" in code, "单参调用不得带第二个实参"
        ast.parse(code)

    def test_no_boundary_single_param_binds_zero(self):
        """无边界材料时按签名首参做保守 0 绑定（元数正确）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "double",
            "preconditions": ["value >= 0"],
            "postconditions": ["r >= 0"],
            "invariants": [],
            "boundaries": [],
            "oracle_kind": "postcondition",
        }
        code = compile_spec_oracle(spec, "m", "double", signature_params=["value"])
        assert "value = 0" in code
        assert "double(value)" in code
        ast.parse(code)

    def test_none_signature_keeps_legacy_binding(self):
        """signature_params=None 时保持历史绑定集合与行为（回归保护）。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "f",
            "preconditions": [],
            "postconditions": ["r > 0"],
            "invariants": [],
            "boundaries": [{"input": 5, "expected": 6, "rationale": ""}],
            "oracle_kind": "postcondition",
        }
        code = compile_spec_oracle(spec, "m", "f", signature_params=None)
        assert "x = 5" in code, "历史口径：边界输入绑定到 x"
        assert "f(x)" in code
        ast.parse(code)

    def test_zero_param_with_boundary_skips(self):
        """0 参函数 + 边界材料：元数不匹配 → 保守返回空串。"""
        spec = {
            "schema_version": "1",
            "source": "test",
            "function_name": "answer",
            "preconditions": [],
            "postconditions": ["r == 42"],
            "invariants": [],
            "boundaries": [{"input": 1, "expected": 42, "rationale": ""}],
            "oracle_kind": "postcondition",
        }
        assert compile_spec_oracle(spec, "m", "answer", signature_params=[]) == ""


# ─── R1c：确定性规约 oracle 执行接线 ────────────────────────────────────────


class TestSpecOracleInjection:
    """R1c：_append_spec_oracle_to_test 的注入/降级口径。"""

    def test_injection_appends_oracle_test(self):
        """有效规约材料时把编译产物追加到 LLM 测试尾部。"""
        from src.graph.nodes import _append_spec_oracle_to_test, _spec_oracle_exec_enabled

        assert _spec_oracle_exec_enabled() is False, "SPEC_ORACLE_EXEC_ENABLE 默认关"

        state = {
            "spec_ir": {
                "schema_version": "1",
                "source": "test",
                "function_name": "double",
                "preconditions": [],
                "postconditions": ["r == x * 2"],
                "invariants": [],
                "boundaries": [{"input": 4, "expected": 8, "rationale": ""}],
                "oracle_kind": "postcondition",
            },
            "target_code": "def double(x):\n    return x * 2\n",
            "target_function": "double",
            "module_name": "target_mod",
        }
        merged, injected = _append_spec_oracle_to_test("def test_llm():\n    pass\n", state)  # type: ignore[arg-type]
        assert injected is True
        assert "def test_llm" in merged, "原 LLM 测试保留"
        assert "test_specir_v2_oracle" in merged, "规约 oracle 测试被追加"
        assert merged.index("def test_llm") < merged.index("test_specir_v2_oracle")
        ast.parse(merged)

    def test_fallback_parses_logic_analysis_from_test_plan(self):
        """state 无 spec_ir 时现场解析 test_plan.logic_analysis（两级降级）。

        单参签名 + 无边界材料：层 2 保守 0 绑定（value = 0）+ 可编译
        后置条件 → 注入成功（签名感知让"无边界"场景也可产确定性 oracle）。
        """
        from src.graph.nodes import _append_spec_oracle_to_test

        state = {
            "test_plan": {
                "logic_analysis": {
                    "function_name": "double",
                    "postconditions": ["r == x * 2"],
                    "edge_cases": [],
                }
            },
            "target_code": "def double(x):\n    return x * 2\n",
            "target_function": "double",
            "module_name": "target_mod",
        }
        merged, injected = _append_spec_oracle_to_test("pass\n", state)  # type: ignore[arg-type]
        assert injected is True
        assert "test_specir_v2_oracle" in merged
        assert "x = 0" in merged, "无边界时按签名首参保守 0 绑定"
        ast.parse(merged)

    def test_no_material_no_injection(self):
        """无规约材料 / 无函数名时原文返回不注入。"""
        from src.graph.nodes import _append_spec_oracle_to_test

        for state in ({}, {"spec_ir": None, "target_function": "f", "module_name": "m"}, {"spec_ir": {}}):
            merged, injected = _append_spec_oracle_to_test("CODE", state)  # type: ignore[arg-type]
            assert (merged, injected) == ("CODE", False)


# ─── R4b：patch_rollback fail-closed 口径 ────────────────────────────────────


class TestPatchRollbackFailClosed:
    """R4b：rc>=2 / 超时 / IO 异常的 fail-closed 改判口径。"""

    def test_collection_error_kept_open_by_default(self):
        """默认（fail_closed=False）：收集错误归 regression_error（历史口径）。"""
        # 模块级断言在收集期失败 → pytest rc=2（真实子进程）
        bad_test = "import nonexistent_module_xyz\n\ndef test_x():\n    assert True\n"
        result = run_p2p_regression("def f():\n    pass\n", bad_test, "m", fail_closed=False)
        assert result["verdict"] == "regression_error"

    def test_collection_error_rolls_back_when_fail_closed(self):
        """fail_closed=True：收集错误改判 regression_failed（触发回滚）。"""
        bad_test = "import nonexistent_module_xyz\n\ndef test_x():\n    assert True\n"
        result = run_p2p_regression("def f():\n    pass\n", bad_test, "m", fail_closed=True)
        assert result["verdict"] == "regression_failed"

    def test_assertion_failure_always_rolls_back(self):
        """断言级失败（rc=1）两种口径均 regression_failed（不变量）。"""
        failing_test = "from m import f\n\ndef test_x():\n    assert f() == 999\n"
        code = "def f():\n    return 1\n"
        assert run_p2p_regression(code, failing_test, "m", fail_closed=False)["verdict"] == "regression_failed"
        assert run_p2p_regression(code, failing_test, "m", fail_closed=True)["verdict"] == "regression_failed"

    def test_protocol_run_transparent_fail_closed(self):
        """PatchRollbackProtocol.run 透传 fail_closed：坏测试时补丁被回滚。"""
        protocol = PatchRollbackProtocol()
        original = "def f():\n    return 1\n"
        patch = "def f():\n    return 2\n"
        bad_test = "import nonexistent_module_xyz\n\ndef test_x():\n    assert True\n"

        def apply_fn(code: str, p: str):
            return p, True

        result_open = protocol.run(
            original, patch, test_code=bad_test, module_name="m", apply_fn=apply_fn, fail_closed=False
        )
        assert result_open["verdict"] == "regression_error"
        assert result_open["rolled_back"] is False, "历史口径：坏测试不误杀补丁"

        result_closed = protocol.run(
            original, patch, test_code=bad_test, module_name="m", apply_fn=apply_fn, fail_closed=True
        )
        assert result_closed["verdict"] == "regression_failed"
        assert result_closed["rolled_back"] is True, "fail-closed：回归无法裁决 → 回滚"
        assert result_closed["applied_code"] == original


# ─── R17：结构化路由信号 ─────────────────────────────────────────────────────


class TestStructuredRoutingSignal:
    """R17：_test_gen_signal_hit 的结构化优先 + 关键词兜底口径。"""

    def test_default_off_keyword_fallback_only(self):
        """ROUTE_STRUCTURED_ENABLE 默认关：error_category 不参与判定（历史口径）。"""
        from src.graph.workflow import _test_gen_signal_hit

        state = {"error_category": "logic_error", "diagnosis": "源码逻辑缺陷"}
        hit, source = _test_gen_signal_hit(state, "源码逻辑缺陷")  # type: ignore[arg-type]
        assert (hit, source) == (False, ""), "开关关时仅关键词口径（本例无关键词）"

    def test_structured_signal_when_enabled(self, monkeypatch):
        """开关开 + logic_error：无关键词也命中，来源标 structured。"""
        monkeypatch.setenv("ROUTE_STRUCTURED_ENABLE", "true")
        from src.graph.workflow import _test_gen_signal_hit

        state = {"error_category": "logic_error", "diagnosis": "源码逻辑缺陷"}
        hit, source = _test_gen_signal_hit(state, "源码逻辑缺陷")  # type: ignore[arg-type]
        assert (hit, source) == (True, "structured_error_category")

    def test_keyword_fallback_when_no_category(self, monkeypatch):
        """开关开但无 error_category：关键词兜底命中。"""
        monkeypatch.setenv("ROUTE_STRUCTURED_ENABLE", "true")
        from src.graph.workflow import _test_gen_signal_hit

        hit, source = _test_gen_signal_hit({"error_category": None}, "测试用例期望值写反")  # type: ignore[arg-type]
        assert (hit, source) == (True, "diagnosis_keyword")

    def test_structured_priority_over_keyword(self, monkeypatch):
        """两信号同时命中时结构化优先（来源标签可度量兜底触发率）。"""
        monkeypatch.setenv("ROUTE_STRUCTURED_ENABLE", "true")
        from src.graph.workflow import _test_gen_signal_hit

        hit, source = _test_gen_signal_hit({"error_category": "logic_error"}, "测试用例期望值写反")  # type: ignore[arg-type]
        assert (hit, source) == (True, "structured_error_category")

    def test_should_debug_regenerates_on_structured_signal(self, monkeypatch):
        """集成：开关开 + logic_error + 早期迭代 → 路由 regenerate（而非 debug）。"""
        monkeypatch.setenv("ROUTE_STRUCTURED_ENABLE", "true")
        from src.graph.workflow import _should_debug

        state = {
            "test_passed": False,
            "iteration": 0,
            "max_iterations": 3,
            "error_category": "logic_error",
            "diagnosis": "断言失败但栈未触及被测模块",
            "repair_history": [],
            "regeneration_count": 0,
        }
        assert _should_debug(state) == "regenerate"  # type: ignore[arg-type]

    def test_should_debug_debug_path_default_off(self):
        """开关关时同状态走 debug（历史口径回归保护）。"""
        from src.graph.workflow import _should_debug

        state = {
            "test_passed": False,
            "iteration": 0,
            "max_iterations": 3,
            "error_category": "logic_error",
            "diagnosis": "断言失败但栈未触及被测模块",
            "repair_history": [],
            "regeneration_count": 0,
        }
        assert _should_debug(state) == "debug"  # type: ignore[arg-type]


# ─── R15：AITESTER_PROFILE 预设 ──────────────────────────────────────────────


class TestProfilePresets:
    """R15：_apply_profile_presets 的 setdefault 注入口径。"""

    @pytest.fixture(autouse=True)
    def _cleanup_env(self):
        """清理 setdefault 注入的键（setdefault 绕过 monkeypatch 追踪）。"""
        keys = [
            "AITESTER_PROFILE",
            *dict.fromkeys(
                k
                for presets in (
                    {
                        "KERNEL_SANDBOX_ENABLE": "true",
                        "PATCH_SNAPSHOT_ROLLBACK_ENABLE": "true",
                        "PATCH_ROLLBACK_FAIL_CLOSED": "true",
                        "INJECTION_GUARD_ENABLE": "true",
                        "ROGUE_MONITOR_ENABLE": "true",
                        "FLAKY_CHECK_ENABLE": "true",
                    },
                    {
                        "SPEC_IR_ENABLE": "true",
                        "SPEC_IR_DSL_ENABLE": "true",
                        "SPEC_ORACLE_EXEC_ENABLE": "true",
                        "ENABLE_MUTATION_SCORING": "true",
                        "ORACLE_VALIDATE_ENABLE": "true",
                    },
                )
                for k in presets
            ),
        ]
        saved = {k: os.environ.get(k) for k in keys}
        yield
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_safe_profile_injects_presets(self, monkeypatch):
        """safe 档注入安全开关且不覆盖用户显式设置。"""
        from config import _apply_profile_presets

        monkeypatch.setenv("AITESTER_PROFILE", "safe")
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "false")  # 显式设置优先
        profile = _apply_profile_presets()
        assert profile == "safe"
        assert os.environ.get("KERNEL_SANDBOX_ENABLE") == "false", "显式设置不被覆盖"
        assert os.environ.get("PATCH_ROLLBACK_FAIL_CLOSED") == "true", "未显式设置的键被注入"

    def test_scientific_profile_injects_eval_switches(self, monkeypatch):
        """scientific 档注入评测链路开关。"""
        from config import _apply_profile_presets

        monkeypatch.setenv("AITESTER_PROFILE", "scientific")
        assert _apply_profile_presets() == "scientific"
        assert os.environ.get("SPEC_ORACLE_EXEC_ENABLE") == "true"
        assert os.environ.get("ENABLE_MUTATION_SCORING") == "true"

    def test_unknown_profile_ignored(self, monkeypatch):
        """未识别 profile 记 WARNING 并忽略（不注入任何键）。"""
        from config import _apply_profile_presets

        monkeypatch.setenv("AITESTER_PROFILE", "yolo")
        assert _apply_profile_presets() is None

    def test_unset_profile_noop(self, monkeypatch):
        """未设置 profile 时返回 None 零注入。"""
        from config import _apply_profile_presets

        monkeypatch.delenv("AITESTER_PROFILE", raising=False)
        assert _apply_profile_presets() is None


# ─── R16：rogue_monitor 接线 ─────────────────────────────────────────────────


class TestRogueMonitorWiring:
    """R16：base_agent 调用层上报 + 开关默认关。"""

    def test_switch_default_off(self):
        """ROGUE_MONITOR_ENABLE 默认关（历史口径零开销）。"""
        from src.agents.rogue_monitor import reset_rogue_monitor, rogue_monitor_enabled

        reset_rogue_monitor()
        assert rogue_monitor_enabled() is False

    @patch("src.agents.base_agent._get_or_create_chat_client")
    @patch("src.agents.base_agent._get_llm_config")
    def test_llm_call_reports_event_when_enabled(self, mock_config, mock_client, monkeypatch):
        """开关开时 _call_llm_with_cache 上报事件到监控单例。"""
        from src.agents.base_agent import BaseAgent
        from src.agents.rogue_monitor import get_rogue_monitor, reset_rogue_monitor

        mock_config.return_value = ("k", "http://localhost", "m")
        mock_client.return_value = MagicMock()
        monkeypatch.setenv("ROGUE_MONITOR_ENABLE", "true")
        reset_rogue_monitor()
        try:
            agent = BaseAgent("prompt")
            with patch.object(BaseAgent, "_call_llm", return_value="resp") as mock_call:
                out = agent._call_llm_with_cache("hello")
            assert out == "resp"
            mock_call.assert_called_once()
            monitor = get_rogue_monitor()
            window = monitor._events.get("BaseAgent")
            assert window and len(window) == 1, "LLM 调用应上报一次事件"
        finally:
            reset_rogue_monitor()
            monkeypatch.delenv("ROGUE_MONITOR_ENABLE", raising=False)


# ─── R11：确定性采样级联 ─────────────────────────────────────────────────────


class TestDeterministicTemperature:
    """R11：_apply_deterministic_temperature 三处级联。"""

    def test_cascade_sets_all_three_namespaces(self, monkeypatch):
        """os.environ / config.TEMPERATURE / base_agent.TEMPERATURE 三处同步为 0.0。"""
        import config as config_module
        import src.agents.base_agent as base_agent_module
        from experiments.run_benchmark import _apply_deterministic_temperature

        monkeypatch.setenv("TEMPERATURE", "0.7")
        orig_config_t = config_module.TEMPERATURE
        orig_ba_t = base_agent_module.TEMPERATURE
        try:
            _apply_deterministic_temperature()
            assert os.environ["TEMPERATURE"] == "0.0"
            assert config_module.TEMPERATURE == 0.0
            assert base_agent_module.TEMPERATURE == 0.0
        finally:
            config_module.TEMPERATURE = orig_config_t
            base_agent_module.TEMPERATURE = orig_ba_t
