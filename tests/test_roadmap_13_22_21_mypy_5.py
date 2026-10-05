"""
1.3 分层压缩降级链 / 2.2 补丁后处理重采样 / 2.1 mypy 静态层 /
五、多维度污染检测 的单元测试（无 LLM 调用，纯静态）。
"""

from __future__ import annotations

import os

import pytest


# ─── 1.3 分层压缩降级链（patch_applier.build_tiered_context / advance_context_tier）
class TestTieredContext:
    """三级上下文档位构建（L0 full_context / L1 patch_ingredients / L2 minimal）。"""

    SRC = """
import os
__all__ = ['alpha', 'beta']

def alpha(x):
    return x + 1

def beta(a, b):
    return a * b

def helper(a, b):
    return a - b
"""

    @pytest.fixture(autouse=True)
    def _reset_tier(self, monkeypatch):
        monkeypatch.delenv("CONTEXT_TIER", raising=False)
        from src.tools import patch_applier

        patch_applier._CONTEXT_TIER_INDEX = 0

    def test_tier0_full_context(self):
        from src.tools.patch_applier import build_tiered_context

        ctx = build_tiered_context(self.SRC, "alpha", tier=0)
        assert "def alpha" in ctx
        assert "def helper" not in ctx  # L0 = extract_function_context 口径
        assert "def beta" not in ctx

    def test_tier1_patch_ingredients(self):
        from src.tools.patch_applier import build_tiered_context

        ctx = build_tiered_context(self.SRC, "alpha", tier=1)
        assert "[PATCH_INGREDIENTS]" in ctx
        assert "def alpha" in ctx
        # 导出契约符号必须保留
        assert "alpha" in ctx and "beta" in ctx

    def test_tier2_minimal(self):
        from src.tools.patch_applier import build_tiered_context

        ctx = build_tiered_context(self.SRC, "alpha", tier=2)
        assert "[MINIMAL_CONTEXT]" in ctx
        assert "must_keep_symbols" in ctx
        assert "def alpha" in ctx
        # L2 极简：函数体被省略（仅保留 def 行）
        assert "return x + 1" not in ctx

    def test_no_fallback_across_tiers(self):
        """指定 L2 就构建 L2，不因 L2 构建失败落到 L3（档位语义不漂移）。"""
        from src.tools.patch_applier import build_tiered_context

        # 无顶层函数的代码 → L2 minimal 构建后 parts 为空 → 返回空串
        empty_src = "x = 1\ny = 2\n"
        assert build_tiered_context(empty_src, "nope", tier=2) == ""

    def test_advance_context_tier_caps_at_minimal(self, monkeypatch):
        from src.tools.patch_applier import _current_context_tier, advance_context_tier

        assert _current_context_tier() == ("full_context", 0, 0.2)
        idx = advance_context_tier()
        assert idx == 1
        assert _current_context_tier()[0] == "patch_ingredients"
        advance_context_tier()
        assert _current_context_tier() == ("minimal", 2, 0.0)
        # 封顶 2（minimal 不再降级）
        advance_context_tier()
        assert _current_context_tier() == ("minimal", 2, 0.0)

    def test_advance_syncs_env_var(self, monkeypatch):
        monkeypatch.delenv("CONTEXT_TIER", raising=False)
        from src.tools.patch_applier import advance_context_tier

        advance_context_tier()
        assert os.environ.get("CONTEXT_TIER") == "1"


# ─── 2.2 重采样接线（_patch_applier_node 在应用失败时触发 apply_patch_with_resample）
class TestPatchResampleWiring:
    """PATCH_RESAMPLE_ENABLE=true 时 _patch_applier_node 走重采样路径。"""

    def test_disabled_by_default(self):
        from src.graph.nodes import _patch_resample_enabled

        assert _patch_resample_enabled() is False

    def test_enabled(self, monkeypatch):
        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        from src.graph.nodes import _patch_resample_enabled

        assert _patch_resample_enabled() is True

    def test_max_clamped_to_5(self, monkeypatch):
        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "99")
        from src.graph.nodes import _patch_resample_max

        assert _patch_resample_max() == 5
        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "0")
        assert _patch_resample_max() == 0
        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "abc")
        assert _patch_resample_max() == 2


# ─── 2.1 mypy 静态层（type_repair._run_mypy_findings）
class TestMypyStaticLayer:
    """TYPE_CHECK_ENABLE=true 且 mypy 已安装时，_run_mypy_findings 补充疑点。"""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        from src.tools.type_repair import _run_mypy_findings

        findings = _run_mypy_findings(
            original_code="def f():\n    return 1\n",
            patched_code="def f():\n    return undefined_name\n",
        )
        assert findings == []

    def test_mypy_not_installed_returns_empty(self, monkeypatch):
        """mypy 未安装时透明降级为空列表（不阻断 ast 静态层）。

        通过 sys.modules 注入 ImportError 模拟 "mypy.api 不可用"，
        验证保守降级路径。
        """
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        import sys

        _real_mypy_api = sys.modules.get("mypy.api")
        try:
            # 让 `import mypy.api` 抛 ImportError
            sys.modules["mypy.api"] = None  # type: ignore
            # 触发 _run_mypy_findings 的 try import 路径
            from src.tools.type_repair import _run_mypy_findings

            findings = _run_mypy_findings(
                original_code="def f():\n    return 1\n",
                patched_code="def f():\n    return x\n",
            )
            # mypy 不可用 → 空列表（保守）
            assert findings == []
        finally:
            if _real_mypy_api is not None:
                sys.modules["mypy.api"] = _real_mypy_api
            elif "mypy.api" in sys.modules:
                del sys.modules["mypy.api"]

    def test_enabled_with_real_mypy_no_exception(self, monkeypatch):
        """mypy 已安装时 _run_mypy_findings 不抛异常（保守降级）。"""
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        from src.tools.type_repair import _run_mypy_findings

        # 用一个明显类型错误的代码（未定义名称），若 mypy 装了会报 [name-defined]
        # 无论 mypy 装没装都不应抛异常（保守降级）
        _ = _run_mypy_findings(
            original_code="def f():\n    return 1\n",
            patched_code="def f():\n    return totally_undefined_symbol\n",
        )


# ─── 2.2 refine_failure_category 消费 patch_syntax_invalid
class TestRefinePatchSyntaxInvalid:
    """patch_syntax_invalid 标记经 refine_failure_category 归一为
    PATCH_SYNTAX_INVALID 类别。"""

    def test_flag_triggers_category(self):
        from src.agents.error_classifier import ErrorCategory, refine_failure_category

        cat = refine_failure_category(
            error_category="assertion",
            test_passed=False,
            repair_history=[],
            rag_stats=[],
            execution_trace=[{"iteration": 1, "passed": False}],
            patch_syntax_invalid=True,
        )
        assert cat == ErrorCategory.PATCH_SYNTAX_INVALID.value

    def test_error_category_string_direct(self):
        from src.agents.error_classifier import ErrorCategory, refine_failure_category

        cat = refine_failure_category(
            error_category=ErrorCategory.PATCH_SYNTAX_INVALID.value,
            test_passed=False,
            repair_history=[],
            rag_stats=[],
            execution_trace=[{"iteration": 1, "passed": False}],
        )
        assert cat == ErrorCategory.PATCH_SYNTAX_INVALID.value

    def test_no_flag_no_category(self):
        from src.agents.error_classifier import refine_failure_category

        cat = refine_failure_category(
            error_category="assertion",
            test_passed=False,
            repair_history=[],
            rag_stats=[],
            execution_trace=[{"iteration": 1, "passed": False}],
            patch_syntax_invalid=False,
        )
        assert cat == "assertion"


# ─── 五、contamination_risk_level 写进 details[]
class TestContaminationRiskLevelInDetails:
    """_build_task_result 的 details[] 行携带 contamination_risk_level 字段。"""

    def _make_task(self):
        from src.datasets.dataset_loader import BenchmarkTask

        return BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="p",
            instance_code="def f():\n    return 1\n",
            test_code="def test_f():\n    assert f() == 1\n",
            expected_pass_count=1,
            total_test_count=1,
            metadata={},
        )

    def test_no_golden_not_applicable(self):
        from experiments.run_benchmark import _build_task_result

        task = self._make_task()
        result = _build_task_result(task, 1.0, final_state={"patch": "def f():\n    return 1\n"})
        # N7（2026-10-05 复审）：合成数据集无 golden patch → 检测不适用，
        # 不再标 "low"（"检测没有发生"≠"检测过且无重叠证据"）
        assert result["contamination_risk_level"] == "not_applicable"
        assert "contract_missing_symbols" in result
        assert "patch_resample_stats" in result

    def test_with_golden_high_for_identical(self):
        from experiments.run_benchmark import _build_task_result

        task = self._make_task()
        g = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-def f():\n"
            "-    return 1\n"
            "+def f():\n"
            "+    return 2\n"
        )
        golden_patches = {"t1": g}
        result = _build_task_result(
            task,
            1.0,
            final_state={"patch": g},
            golden_patches=golden_patches,
        )
        # 生成补丁 = 黄金补丁 → 至少一个维度 high → 综合 high
        assert result["contamination_risk_level"] == "high"
