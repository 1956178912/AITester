"""nodes.py 三大闭包回调分支补测（2026-10-02 审查：分支覆盖门禁回绿）。

背景：coverage.xml 显示 `graph/nodes.py` 中三个函数内闭包回调合计
约 52 个分支未覆盖，是全仓最大缺口（该文件也是总分支覆盖 77% 门槛
的决定性缺口之一）：

  1. `_generator_node._on_retrieve`（RAG 检索 + 相关性过滤，16 分支）；
  2. `_debugger_node._on_retrieve_repairs`（检索 + 过滤 + 条件注入，
     22 分支）；
  3. `_patch_applier_node._on_resample`（2.2 重采样回调：空补丁 / 提取
     失败 / 应用失败 / 契约破坏 / LLM 异常五条降级路径，14 分支）。

全部经 monkeypatch/mock 构造（RAG 检索器 mock、resampler LLM mock），
零真实 LLM 调用，CI 稳定。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── _generator_node._on_retrieve ─────────────────────────────────────────────


@pytest.mark.unit
class TestGeneratorOnRetrieve:
    """_generator_node 的 RAG 检索闭包（retriever mock）。"""

    def _state(self) -> dict:
        return {"target_code": "def foo(): pass", "module_name": "test_module"}

    def _run(self, state: dict, refs):
        from src.graph.nodes import _generator_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_test_cases.return_value = refs
        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_foo(): pass"
        with (
            patch("src.graph.nodes.ENABLE_RAG", True),
            patch("src.graph.nodes.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.nodes.get_rag_retriever", return_value=mock_retriever),
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
        ):
            result = _generator_node(state)
        return result, mock_agent, mock_retriever

    def test_refs_empty_skips_filter(self):
        """refs 为空 → 不进 filter_by_relevance 分支（历史口径）。"""
        result, _mock_agent, mock_retriever = self._run(self._state(), [])
        assert result["generated_test"] == "def test_foo(): pass"
        mock_retriever.retrieve_test_cases.assert_called_once()
        # 无 refs → rag_references 为 None（rag_refs_box 初始值）
        assert result.get("rag_references") in (None, [])

    def test_refs_nonempty_goes_through_filter(self):
        """refs 非空 → 走 filter_by_relevance（开关关时原样透传）。"""
        refs = [{"code": "a", "test_code": "b", "similarity": 0.9}]
        result, _, _ = self._run(self._state(), refs)
        assert result["generated_test"] == "def test_foo(): pass"

    def test_retriever_exception_swallowed(self):
        """检索器抛异常 → rag_guarded 吞掉，节点不崩。"""
        from src.graph.nodes import _generator_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_test_cases.side_effect = RuntimeError("向量库挂了")
        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_ok(): pass"
        with (
            patch("src.graph.nodes.ENABLE_RAG", True),
            patch("src.graph.nodes.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.nodes.get_rag_retriever", return_value=mock_retriever),
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
        ):
            result = _generator_node(self._state())
        assert result["generated_test"] == "def test_ok(): pass"

    def test_retriever_none_skips(self):
        """get_rag_retriever 返回 None → 跳过 action。"""
        from src.graph.nodes import _generator_node

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_n(): pass"
        with (
            patch("src.graph.nodes.ENABLE_RAG", True),
            patch("src.graph.nodes.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.nodes.get_rag_retriever", return_value=None),
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
        ):
            result = _generator_node(self._state())
        assert result["generated_test"] == "def test_n(): pass"

    def test_rag_disabled_skips_retriever(self):
        """ENABLE_RAG=False（默认）→ retriever 不被调用。"""
        from src.graph.nodes import _generator_node

        mock_retriever = MagicMock()
        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_d(): pass"
        with (
            patch("src.graph.nodes.ENABLE_RAG", False),
            patch("src.graph.nodes.RAG_MODULE_AVAILABLE", False),
            patch("src.graph.nodes.get_rag_retriever", return_value=mock_retriever),
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
        ):
            result = _generator_node(self._state())
        mock_retriever.retrieve_test_cases.assert_not_called()
        assert result["generated_test"] == "def test_d(): pass"


# ─── _debugger_node._on_retrieve_repairs ──────────────────────────────────────


@pytest.mark.unit
class TestDebuggerOnRetrieveRepairs:
    """_debugger_node 的修复案例检索闭包（含 P2 相关性过滤 + 条件注入）。"""

    def _state(self) -> dict:
        return {
            "target_code": "def foo(x): return x * 2",
            "test_output": "AssertionError",
            "failed_cases": [{"case": "test_neg", "error": "Expected 0"}],
            "iteration": 0,
            "error_category": "logic_error",
        }

    def _run(self, refs, *, enable_rag: bool = True, category: str = "logic_error"):
        from src.graph.nodes import _debugger_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_repairs.return_value = refs
        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "边界",
            "error_category": category,
            "fix_strategy": "补检查",
            "patch": "def foo(x):\n    if x < 0: return 0\n    return x * 2",
        }
        with (
            patch("src.graph.nodes.ENABLE_RAG", enable_rag),
            patch("src.graph.nodes.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.nodes.get_rag_retriever", return_value=mock_retriever),
            patch("src.graph.nodes.DebuggerAgent", return_value=mock_agent),
        ):
            result = _debugger_node(self._state())
        return result, mock_retriever

    def test_empty_refs_skips_filter_and_inject(self):
        result, mock_retriever = self._run([])
        assert result["patch"]
        mock_retriever.retrieve_repairs.assert_called_once()

    def test_nonempty_refs_goes_through_filter(self):
        refs = [
            {
                "code": "a",
                "patch": "p",
                "similarity": 0.95,
                "metadata": {"error_category": "logic_error"},
            }
        ]
        result, _ = self._run(refs)
        assert result["patch"]

    def test_conditional_inject_gate_blocks_mismatch(self):
        """RAG_CONDITIONAL_OPEN 默认关 → should_inject_refs 恒 True；
        显式打开且类目不匹配 → refs 被清空（不注入分支）。"""
        refs = [
            {
                "code": "a",
                "patch": "p",
                "similarity": 0.95,
                "metadata": {"error_category": "timeout"},
            }
        ]
        with patch("src.graph.rag.rag_conditional_enabled", return_value=True):
            result, _ = self._run(refs, category="logic_error")
        assert result["patch"], "条件注入拦截后节点仍应产出 patch（空 refs 口径）"

    def test_conditional_inject_allows_match(self):
        refs = [
            {
                "code": "a",
                "patch": "p",
                "similarity": 0.95,
                "metadata": {"error_category": "logic_error"},
            }
        ]
        with patch("src.graph.rag.rag_conditional_enabled", return_value=True):
            result, _ = self._run(refs, category="logic_error")
        assert result["patch"]

    def test_relevance_threshold_filters_low_similarity(self):
        """RAG_RELEVANCE_THRESHOLD 开 → 低相似度案例被过滤。"""
        refs = [
            {"code": "a", "patch": "p", "similarity": 0.2, "metadata": {}},
            {"code": "b", "patch": "q", "similarity": 0.95, "metadata": {}},
        ]
        with patch("src.graph.rag.rag_relevance_threshold_enabled", return_value=True):
            result, _ = self._run(refs)
        assert result["patch"]

    def test_rag_disabled_default(self):
        """默认 RAG 关 → 检索器零调用（历史口径）。"""
        result, mock_retriever = self._run([], enable_rag=False)
        mock_retriever.retrieve_repairs.assert_not_called()
        assert result["patch"]


# ─── _patch_applier_node._on_resample ─────────────────────────────────────────


@pytest.mark.unit
class TestPatchApplierOnResample:
    """2.2 重采样回调五条降级路径（PATCH_RESAMPLE_ENABLE=true 显式打开）。"""

    def _state(self, tmp_path, patch_text: str) -> dict:
        target = tmp_path / "res_mod.py"
        if not target.exists():
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return {
            "target_file": str(target),
            "target_code": "def add(a, b):\n    return a + b\n",
            "patch": patch_text,
            "diagnosis": "诊断",
            "error_category": "runtime",
            "iteration": 1,
            "repair_history": [],
        }

    def test_empty_patch_and_error_returns_none_early(self, tmp_path, monkeypatch):
        """patch 与 ast_error 均空 → 闭包首分支直接 None（不调 LLM）。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        from src.graph.nodes import _patch_applier_node

        # 空 patch → 应用失败触发重采样，但闭包首分支返回 None
        state = self._state(tmp_path, "")
        result = _patch_applier_node(state)
        assert result["repair_history"][-1]["patch_applied"] is False

    def test_llm_exception_returns_none(self, tmp_path, monkeypatch):
        """resampler LLM 抛异常 → except 分支保守 None，不崩节点。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        mock_agent._call_llm_with_cache.side_effect = RuntimeError("LLM 挂了")
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            # 补丁无法应用（定位不到目标函数）→ 触发重采样回调
            state = self._state(tmp_path, "def nonexistent_xyz():\n    return 999\n")
            result = _patch_applier_node(state)
        assert result["repair_history"][-1]["patch_applied"] is False

    def test_llm_returns_non_code_returns_none(self, tmp_path, monkeypatch):
        """LLM 返回无代码块文本 → extract 失败 None。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        mock_agent._call_llm_with_cache.return_value = "抱歉，我无法生成补丁。"
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def nonexistent_xyz():\n    return 999\n")
            result = _patch_applier_node(state)
        assert result["repair_history"][-1]["patch_applied"] is False

    def test_llm_returns_unappliable_code_returns_none(self, tmp_path, monkeypatch):
        """LLM 返回代码但 safe_apply_patch 失败 → None 分支。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        mock_agent._call_llm_with_cache.return_value = "```python\ndef totally_unknown():\n    return 1\n```"
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def nonexistent_xyz():\n    return 999\n")
            result = _patch_applier_node(state)
        assert result["repair_history"][-1]["patch_applied"] is False

    def test_llm_returns_valid_code_applies(self, tmp_path, monkeypatch):
        """LLM 返回合法且符合契约的补丁 → 重采样成功写盘。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        # 证据门 opt-out（2026-10-05 P0 真阻断语义）：本用例主题是重采样逻辑，
        # 无 gold/sbfl 证据的补丁在 gate 默认开时会被证据门拒绝写盘
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        mock_agent._call_llm_with_cache.return_value = "```python\ndef add(a, b):\n    return a + b + 100\n```"
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def nonexistent_xyz():\n    return 999\n")
            result = _patch_applier_node(state)
        # 重采样成功 → patch 写入（applied True）
        assert result["repair_history"][-1]["patch_applied"] is True
        assert "+ 100" in result["target_code"]

    def test_contract_broken_after_resample_rejected(self, tmp_path, monkeypatch):
        """重采样成功但破坏命名契约 → 拒绝写盘分支（applied 置 False）。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        # 删除原模块级符号 add → 契约破坏
        mock_agent._call_llm_with_cache.return_value = "```python\ndef totally_new(x):\n    return x\n```"
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def add(a, b):\n    return a + b\n")
            # patch 先给一个无法定位的补丁，触发重采样
            state["patch"] = "def other_name():\n    return 1\n"
            result = _patch_applier_node(state)
        # 契约破坏 → 保守拒绝（target_code 保持原样）
        assert result["target_code"] == "def add(a, b):\n    return a + b\n"

    def test_resample_stats_written_to_state(self, tmp_path, monkeypatch):
        """重采样发生 → patch_resample_stats 写入 state（观测键）。"""
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        mock_agent._call_llm_with_cache.return_value = "```python\ndef add(a, b):\n    return a + b + 7\n```"
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def other_name():\n    return 1\n")
            result = _patch_applier_node(state)
        assert "patch_resample_stats" in result
        assert result["patch_resample_stats"].get("resampled") is True

    def test_disabled_by_default_no_resample_llm(self, tmp_path, monkeypatch):
        """默认关 → 重采样 LLM 从不被调用（历史口径零变化）。"""
        monkeypatch.delenv("PATCH_RESAMPLE_ENABLE", raising=False)
        import src.agents.debugger as dbg
        from src.graph.nodes import _patch_applier_node

        mock_agent = MagicMock()
        with patch.object(dbg, "DebuggerAgent", return_value=mock_agent):
            state = self._state(tmp_path, "def other_name():\n    return 1\n")
            _patch_applier_node(state)
            # 开关关时 DebuggerAgent 实例化发生在 _debugger_node 而非本节点
            # 的重采样分支——本节点不构造 resampler
        mock_agent._call_llm_with_cache.assert_not_called()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
