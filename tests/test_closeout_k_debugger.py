"""KB 覆盖率收口：`DebuggerAgent.debug` 主流程的开关门控 / 注入 / 重试分支。

动机：`src/agents/debugger.py` 补口前有 76 行未覆盖，缺口不在纯逻辑辅助方法
（那些已被 `tests/test_debugger_llm_branches.py` 覆盖），而全在 **debug() 主流程
的"默认关"开关路径**——探针/频率/谱系/定位段落注入、跨文件上下文预算、
1.3 降级链温度、P0 4.1 严格 prompt 重试、失败知识库闭环、RAG 判断指令、
对抗性批评者重新生成、编辑意图 + 局部编辑约束、类型修复层修订。这些分支
默认关闭，未覆盖即意味着**"打开后会发生什么"从未被验证过**。

纪律：零 LLM、零网络。`_call_llm_with_cache` 整方法用脚本化队列替换（实例级
monkeypatch，真实方法零调用）；开关一律经 monkeypatch.setenv 显式钉住，不依赖
宿主环境（conftest 的 `_isolate_profile_presets` 不覆盖这批业务开关）。
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

import pytest

from src.agents import debugger as debugger_mod
from src.agents.debugger import DebuggerAgent, _build_downgrade_context

_TARGET_CODE = "def add(a, b):\n    return a - b\n"
_BASE_PATCH = "```python\ndef add(a, b):\n    return a + b\n```"
_TEST_OUTPUT = "AssertionError: assert -1 == 3"
_FAILED_CASES = [{"name": "test_add", "error": "AssertionError: expected 3, got -1"}]


def _reply(**overrides: Any) -> str:
    """构造 debug() 期望的 JSON 响应（默认含一个可应用的最小补丁）。"""
    payload: dict[str, Any] = {
        "root_cause": "加法实现误用了减法",
        "error_category": "assertion",
        "fix_strategy": "把减号改成加号",
        "patch": _BASE_PATCH,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _run_debug(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str],
    **debug_kwargs: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """以脚本化响应队列驱动一次 debug()，返回 (结果, LLM 调用记录)。

    调用记录含 query / temperature / json_mode，供断言"哪段文本进了 prompt"
    "温度是否按降级档位收紧"。
    """
    agent = DebuggerAgent()
    queue: deque[str] = deque(responses)
    calls: list[dict[str, Any]] = []

    def fake_call(
        user_message: str,
        max_retries: int | None = None,
        temperature: float | None = None,
        complexity_class: str | None = None,
        json_mode: bool = False,
    ) -> str:
        calls.append({"query": user_message, "temperature": temperature, "json_mode": json_mode})
        assert queue, f"LLM 调用次数超出脚本预设（第 {len(calls)} 次）"
        return queue.popleft()

    monkeypatch.setattr(agent, "_call_llm_with_cache", fake_call)
    result = agent.debug(
        target_code=_TARGET_CODE,
        test_output=_TEST_OUTPUT,
        failed_cases=list(_FAILED_CASES),
        **debug_kwargs,
    )
    return result, calls


@pytest.mark.unit
class TestInjectionSections:
    """P0 探针 / ANNEAL 频率 / O2 谱系 / FaultLocalizer 定位段注入。"""

    def test_all_optional_sections_appended_to_prompt(self, monkeypatch: pytest.MonkeyPatch):
        result, calls = _run_debug(
            monkeypatch,
            [_reply()],
            probe_section="\n\n【探针快照】frame: add:2",
            failure_frequency_section="【频率强化】优先 oracle_enhancer",
            fl_spectral_section="【谱系先验】嫌疑行 2",
            localization_section="【RGFL 定位】add L2",
        )
        query = calls[0]["query"]
        assert "【探针快照】frame: add:2" in query
        assert "【频率强化】优先 oracle_enhancer" in query
        assert "【谱系先验】嫌疑行 2" in query
        assert "【RGFL 定位】add L2" in query
        # 探针段落被消费的观测位必须同口径为 True（下游实验分析消费该字段）
        assert result["probe_section_applied"] is True

    def test_absent_sections_keep_prompt_byte_identical(self, monkeypatch: pytest.MonkeyPatch):
        """None / 空串不注入（历史 prompt 逐字节不变的保守降级口径）。"""
        result, calls = _run_debug(monkeypatch, [_reply()])
        query = calls[0]["query"]
        for marker in ("【探针快照】", "【频率强化】", "【谱系先验】", "【RGFL 定位】"):
            assert marker not in query
        assert result["probe_section_applied"] is False


@pytest.mark.unit
class TestCrossFileContexts:
    """P0 1.1 跨文件聚焦上下文：模块预算 / 总预算 break。"""

    def test_total_budget_break_drops_trailing_modules(self, monkeypatch: pytest.MonkeyPatch):
        """前两个模块共 3800 字符入 prompt；第三个 +1900 超 4000 预算 → break。"""
        contexts = {
            "mod_a": "A" * 1900,
            "mod_b": "B" * 1900,
            "mod_c": "C" * 1900,
        }
        _, calls = _run_debug(monkeypatch, [_reply()], cross_file_contexts=contexts)
        query = calls[0]["query"]
        assert "【依赖模块 mod_a（调用链聚焦视图）】" in query
        assert "【依赖模块 mod_b（调用链聚焦视图）】" in query
        assert "mod_c" not in query

    def test_single_module_slice_and_injection(self, monkeypatch: pytest.MonkeyPatch):
        """单模块超 2000 字符切片注入；空代码模块按 0 字符计（仍渲染空围栏段）。

        空片段渲染为空围栏是当前实现的保守口径（不跳过模块键、也不臆造内容），
        此处按现状锁定，避免未来"顺手过滤空模块"改变 prompt 字节。
        """
        contexts = {"mod_a": "A" * 2500, "mod_empty": ""}
        _, calls = _run_debug(monkeypatch, [_reply()], cross_file_contexts=contexts)
        query = calls[0]["query"]
        assert "【依赖模块 mod_a（调用链聚焦视图）】" in query
        assert "A" * 2000 in query
        assert "A" * 2001 not in query
        assert "【依赖模块 mod_empty（调用链聚焦视图）】\n```python\n\n```" in query


@pytest.mark.unit
class TestContractDowngradeChain:
    """1.3 分层压缩降级链：收紧上下文 + 档位温度 + 缺失符号负面反馈。"""

    def test_minimal_tier_uses_tiered_context_and_low_temperature(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.tools.patch_applier.build_tiered_context",
            lambda code, focus, tier=None: "【极简档上下文】signature:add(a,b)",
        )
        feedback = {"tier": "minimal", "missing_symbols": ["HELPER_CONST"]}
        result, calls = _run_debug(monkeypatch, [_reply()], contract_reject_feedback=feedback)
        query = calls[0]["query"]
        assert "【极简档上下文】signature:add(a,b)" in query
        assert "【契约守卫负面反馈】" in query
        assert "HELPER_CONST" in query
        # minimal 档位温度映射为 0.0（降级层更低温度，减少创造性改写）
        assert calls[0]["temperature"] == 0.0
        assert result["downgrade_triggered"] is True
        assert result["downgrade_tier"] == "minimal"

    def test_unknown_tier_keeps_caller_temperature(self, monkeypatch: pytest.MonkeyPatch):
        """档位不在映射表 → 温度不收窄（eff_temperature 沿用调用方值）。"""
        monkeypatch.setattr(
            "src.tools.patch_applier.build_tiered_context",
            lambda code, focus, tier=None: "【降级档上下文】",
        )
        result, calls = _run_debug(
            monkeypatch,
            [_reply()],
            contract_reject_feedback={"tier": "no_such_tier", "missing_symbols": []},
            temperature=0.7,
        )
        assert calls[0]["temperature"] == 0.7
        assert result["downgrade_triggered"] is True
        assert result["downgrade_tier"] == "no_such_tier"

    def test_build_failure_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        """档位上下文构建异常 → 空串（调用方回退历史截断口径，不阻断主流程）。"""

        def _boom(code, focus, tier=None):
            raise RuntimeError("AST 解析失败（模拟）")

        monkeypatch.setattr("src.tools.patch_applier.build_tiered_context", _boom)
        assert _build_downgrade_context("def f(): pass\n", None, {"tier": "minimal"}) == ""

    def test_empty_symbols_returns_plain_context(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.tools.patch_applier.build_tiered_context",
            lambda code, focus, tier=None: "【降级档上下文】",
        )
        assert (
            _build_downgrade_context("def f(): pass\n", None, {"tier": "patch_ingredients", "missing_symbols": []})
            == "【降级档上下文】"
        )


@pytest.mark.unit
class TestResponseFormatRetry:
    """P0 4.1：JSON 解析失败后用更严格 prompt 重新请求一次。"""

    def test_strict_retry_success_replaces_raw_response(self, monkeypatch: pytest.MonkeyPatch):
        _, calls = _run_debug(monkeypatch, ["这不是 JSON，只是一段自然语言回答", _reply()])
        assert len(calls) == 2
        assert "【格式要求】只输出一个 JSON 对象" in calls[0]["query"] + calls[1]["query"]
        assert "【格式要求】" not in calls[0]["query"]  # 首次 prompt 不含严格指令
        assert calls[1]["json_mode"] is True
        # 严格重试成功的响应被采用：第二次调用文本是原 query + 格式要求
        assert calls[1]["query"].startswith(calls[0]["query"])
        assert calls[1]["temperature"] == calls[0]["temperature"]


@pytest.mark.unit
class TestFailureKbAndRagInjection:
    """失败知识库闭环（落点 B）与 RAG 判断指令注入。"""

    def test_failure_kb_snippet_injected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.agents.failure_kb.kb_debugger_snippet",
            lambda category: "【失败知识库】同类断言失败优先检查 oracles",
        )
        result, calls = _run_debug(monkeypatch, [_reply()])
        assert "【失败知识库】同类断言失败优先检查 oracles" in calls[0]["query"]
        assert result["kb_prompt_snippet_applied"] is True

    def test_rag_judge_instruction_injected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RAG_JUDGE_INSTRUCTION_ENABLE", "true")
        refs = [{"original_code": "def add(a, b): return a - b", "patch": "def add(a, b): return a + b"}]
        _, calls = _run_debug(monkeypatch, [_reply()], rag_references=refs)
        query = calls[0]["query"]
        assert "以下历史修复案例可作为参考" in query
        assert "【判断指令】" in query
        assert "def add(a, b): return a + b" in query


@pytest.mark.unit
class TestAdversarialCriticRegeneration:
    """3.1 对抗性推理：批评者击穿补丁 → 注入负面反馈重新生成一次。"""

    @staticmethod
    def _responses(regen_patch: str | None) -> list[str]:
        regen = _reply() if regen_patch is None else _reply(patch=regen_patch)
        return [
            json.dumps(["空输入会崩溃", "负数边界"], ensure_ascii=False),
            _reply(),
            json.dumps({"break_cases": ["算 add([], []) 期望抛错却返回 0"], "all_passed": False}, ensure_ascii=False),
            regen,
        ]

    def test_critic_break_regenerates_patch(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "true")
        new_patch = "```python\ndef add(a, b):\n    return a + b  # v2\n```"
        result, calls = _run_debug(monkeypatch, self._responses(new_patch))
        assert len(calls) == 4
        assert "【批评者反馈（3.1）】" in calls[3]["query"]
        assert "算 add([], []) 期望抛错却返回 0" in calls[3]["query"]
        assert "v2" in result["patch"]
        assert result["adversarial_check"]["all_passed"] is False
        assert result["adversarial_check"]["break_cases"] == ["算 add([], []) 期望抛错却返回 0"]

    def test_critic_break_bad_json_keeps_original_patch(self, monkeypatch: pytest.MonkeyPatch):
        """重新生成的响应仍为坏 JSON → 保留原补丁（不因二次格式异常崩溃）。"""
        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "true")
        responses = self._responses(None)
        responses[3] = "仍然不是 JSON"
        result, calls = _run_debug(monkeypatch, responses)
        assert len(calls) == 4
        assert result["patch"] == _BASE_PATCH

    def test_critic_break_identical_patch_keeps_original(self, monkeypatch: pytest.MonkeyPatch):
        """重新生成与原补丁相同 → 不更新补丁（避免无意义覆盖）。"""
        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "true")
        result, calls = _run_debug(monkeypatch, self._responses(None))
        assert len(calls) == 4
        assert result["patch"] == _BASE_PATCH

    def test_critic_all_passed_skips_regeneration(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "true")
        responses = [
            json.dumps(["空输入会崩溃"], ensure_ascii=False),
            _reply(),
            json.dumps({"break_cases": [], "all_passed": True}, ensure_ascii=False),
        ]
        result, calls = _run_debug(monkeypatch, responses)
        assert len(calls) == 3  # 未触发重新生成
        assert result["adversarial_check"]["all_passed"] is True


@pytest.mark.unit
class TestProbeSnapshotLocate:
    """P1 探针快照第二定位源：assertion 失败（无 traceback 行号）也能定位。"""

    def test_probe_frame_locates_function(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PROBE_SNAPSHOT_LOCATE_ENABLE", "true")
        probe_snapshot = {"frames": [{"line": 2, "function": "add", "file": "target_mod.py"}]}
        result, calls = _run_debug(
            monkeypatch,
            [_reply()],
            probe_snapshot=probe_snapshot,
            target_module="target_mod",
        )
        focus = result["position_aware_focus"]
        assert focus["focused"] is True
        assert focus["probe_sourced"] is True
        assert focus["function_name"] == "add"
        assert focus["line"] == 2
        assert "P1 探针快照" in calls[0]["query"]
        assert "`add()`" in calls[0]["query"]

    def test_probe_frame_at_module_level_returns_unfocused(self):
        """探针帧落在模块顶层（无包围函数）→ 保守降级全文件修复。"""
        agent = DebuggerAgent()
        out = agent._locate_repair_focus_from_probe(
            "import os\n\nX = 1\n",
            {"frames": [{"line": 1, "function": "<module>", "file": "m.py"}]},
            None,
        )
        assert out["focused"] is False
        assert out["hint"] == ""
        assert out["probe_sourced"] is True


@pytest.mark.unit
class TestEditIntentLocalized:
    """批次 III 编辑意图落盘 + R4 局部编辑约束/合规观测。"""

    def test_edit_intent_applied_and_localization_observed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        monkeypatch.setenv("LOCALIZED_EDIT_ENABLE", "true")
        localization = {"function_name": "add", "line_start": 2, "line_end": 2}
        response = _reply(
            edit_intents=[{"old_str": "return a - b", "new_str": "return a + b"}],
        )
        result, calls = _run_debug(monkeypatch, [response], localization=localization)
        query = calls[0]["query"]
        assert "【结构化编辑意图（必须输出）】" in query
        assert "【局部编辑约束（定位锚定，LOCALIZED_EDIT_ENABLE）】" in query
        # 确定性引擎把整文件 patch 替换为最小编辑结果
        assert result["edit_intent_status"]["ok"] is True
        assert result["edit_intent_status"]["applied"] == 1
        assert "return a + b" in result["patch"]
        # 合规观测：锚点落在缺陷行窗口内（line 2 ± window 3）
        obs = result["edit_localization"]
        assert obs is not None
        assert obs["constrained"] is True
        assert obs["mode"] == "line"
        assert obs["localized_count"] == 1
        assert obs["total"] == 1
        assert obs["violations"] == []


@pytest.mark.unit
class TestTypeRepairLayer:
    """2.1 类型修复层：LLM 层修订成功 → 补丁替换为修订后代码。"""

    def test_repaired_patch_replaces_original(self, monkeypatch: pytest.MonkeyPatch):
        repaired = "def add(a, b):\n    return a + b  # type-repaired\n"
        monkeypatch.setattr(
            debugger_mod,
            "type_repair_layer",
            lambda original, patched: {"repaired": True, "repaired_code": repaired, "findings": [{"kind": "x"}]},
        )
        result, _ = _run_debug(monkeypatch, [_reply()])
        assert result["type_repair_findings"] == [{"kind": "x"}]
        assert result["patch"] == f"```python\n{repaired}\n```"

    def test_repair_without_code_falls_back_to_patched(self, monkeypatch: pytest.MonkeyPatch):
        """repaired=True 但缺 repaired_code → 用应用后的补丁代码兜底。"""
        monkeypatch.setattr(
            debugger_mod,
            "type_repair_layer",
            lambda original, patched: {"repaired": True, "repaired_code": "", "findings": []},
        )
        result, _ = _run_debug(monkeypatch, [_reply()])
        assert "return a + b" in result["patch"]
        assert result["type_repair_findings"] == []
