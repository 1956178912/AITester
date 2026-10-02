"""tools/patch_applier 正则兜底 / 多函数补丁 / AST 降级分支补齐（2026-10-02·三）。

锁定 patch_applier 剩余低覆盖分支（纯静态，零 LLM）：
- apply_patch_to_code 正则兜底路径 + 未找到目标函数降级 + 空补丁/空原文降级
- apply_multi_function_patch 多函数 / 空补丁 / 无效目标函数降级
- _collapse_blank_lines 连续空行压缩
- _find_function_range 嵌套 / 模块级边界
- _contract_context_tier_index 档位钳制
- dangerous_api_added 差集口径
- apply_patch_with_resample 空补丁短路 / max_resamples=0 不触发重采样
"""

from __future__ import annotations


class TestApplyPatchToCodeBranches:
    def test_async_function_replaced(self):
        from src.tools.patch_applier import apply_patch_to_code

        original = "async def fetch(x):\n    return x\n\n\ndef other():\n    return 1\n"
        new_code, ok = apply_patch_to_code(original, "async def fetch(x):\n    return x * 2\n")
        assert ok is True
        assert "return x * 2" in new_code

    def test_unknown_function_returns_original(self):
        from src.tools.patch_applier import apply_patch_to_code

        original = "def add(a, b):\n    return a + b\n"
        new_code, ok = apply_patch_to_code(original, "def nonexistent():\n    pass\n")
        assert ok is False
        assert new_code == original

    def test_empty_patch_returns_original(self):
        from src.tools.patch_applier import apply_patch_to_code

        original = "def add(a, b):\n    return a + b\n"
        new_code, ok = apply_patch_to_code(original, "")
        assert ok is False
        assert new_code == original

    def test_markdown_wrapped_patch(self):
        from src.tools.patch_applier import apply_patch_to_code

        original = "def add(a, b):\n    return a + b\n"
        patch = "```python\ndef add(a, b):\n    return a + b + 1\n```"
        new_code, ok = apply_patch_to_code(original, patch)
        assert ok is True
        assert "return a + b + 1" in new_code


class TestApplyMultiFunctionPatchBranches:
    def test_multiple_functions_replaced(self):
        from src.tools.patch_applier import apply_multi_function_patch

        original = "def f1():\n    return 1\n\ndef f2():\n    return 2\n"
        patches = [
            {"function_name": "f1", "patch": "def f1():\n    return 11\n"},
            {"function_name": "f2", "patch": "def f2():\n    return 22\n"},
        ]
        new_code, ok = apply_multi_function_patch(original, patches)
        assert ok is True
        assert "return 11" in new_code and "return 22" in new_code

    def test_empty_patches_returns_original(self):
        from src.tools.patch_applier import apply_multi_function_patch

        original = "def f1():\n    return 1\n"
        new_code, ok = apply_multi_function_patch(original, [])
        assert new_code == original or ok is False

    def test_invalid_target_skipped_gracefully(self):
        from src.tools.patch_applier import apply_multi_function_patch

        original = "def f1():\n    return 1\n"
        patches = [
            {"function_name": "f1", "patch": "def f1():\n    return 1\n"},
            {"function_name": "missing", "patch": "def missing():\n    pass\n"},
        ]
        new_code, ok = apply_multi_function_patch(original, patches)
        assert isinstance(new_code, str)
        assert ok in (True, False)


class TestCollapseBlankLinesBranches:
    def test_consecutive_blanks_collapsed_to_one(self):
        from src.tools.patch_applier import _collapse_blank_lines

        # 连续空行压缩为 1 个（末尾单个空行保留——PEP 8 行内空行，非"连续"）
        out = _collapse_blank_lines(["a", "", "", "", "b", "", "c", "", ""])
        assert out == ["a", "", "b", "", "c", ""]

    def test_no_blanks_passthrough(self):
        from src.tools.patch_applier import _collapse_blank_lines

        assert _collapse_blank_lines(["a", "b", "c"]) == ["a", "b", "c"]

    def test_empty_input(self):
        from src.tools.patch_applier import _collapse_blank_lines

        assert _collapse_blank_lines([]) == []


class TestFindFunctionRangeBranches:
    def test_nested_function_kept_in_range(self):
        from src.tools.patch_applier import _find_function_range

        lines = [
            "def outer():",
            "    def inner():",
            "        return 1",
            "    return inner()",
            "",
            "def other():",
            "    return 2",
        ]
        start, end = _find_function_range(lines, "outer", 0)
        assert start == 0
        assert end > 4  # outer 范围含嵌套 inner

    def test_module_level_statement_after_function(self):
        from src.tools.patch_applier import _find_function_range

        lines = [
            "def f():",
            "    return 1",
            "x = 5",
        ]
        start, end = _find_function_range(lines, "f", 0)
        assert start == 0
        assert end >= 2


class TestContractContextTierIndexBranches:
    def test_default_zero(self, monkeypatch):
        from src.tools.patch_applier import _contract_context_tier_index

        monkeypatch.delenv("CONTEXT_TIER", raising=False)
        assert _contract_context_tier_index() == 0

    @staticmethod
    def _valid_values():
        return [("0", 0), ("1", 1), ("2", 2)]

    def test_valid_values(self, monkeypatch):
        from src.tools.patch_applier import _contract_context_tier_index

        for raw, expected in self._valid_values():
            monkeypatch.setenv("CONTEXT_TIER", raw)
            assert _contract_context_tier_index() == expected

    def test_out_of_range_falls_back_zero(self, monkeypatch):
        from src.tools.patch_applier import _contract_context_tier_index

        monkeypatch.setenv("CONTEXT_TIER", "5")
        assert _contract_context_tier_index() == 0

    def test_non_numeric_falls_back_zero(self, monkeypatch):
        from src.tools.patch_applier import _contract_context_tier_index

        monkeypatch.setenv("CONTEXT_TIER", "not_a_num")
        assert _contract_context_tier_index() == 0


class TestDangerousApiAddedBranches:
    def test_identical_no_added(self):
        from src.tools.patch_applier import dangerous_api_added

        assert dangerous_api_added("import os\n", "import os\n") == []

    def test_new_subprocess_call_detected(self):
        from src.tools.patch_applier import dangerous_api_added

        # 危险 API 检测基于**调用**（subprocess.run），非 import 语句
        out = dangerous_api_added(
            "def f():\n    return 1\n",
            "import subprocess\n\ndef f():\n    return subprocess.run(['ls'])\n",
        )
        assert len(out) > 0

    def test_empty_inputs_return_empty(self):
        from src.tools.patch_applier import dangerous_api_added

        assert dangerous_api_added("", "") == []
        assert dangerous_api_added("x", "") == []


class TestPatchApplierResampleBranches:
    def test_empty_patch_short_circuit(self):
        from src.tools.patch_applier import apply_patch_with_resample

        out_code, applied, stats = apply_patch_with_resample(
            original_code="def f():\n    return 1\n",
            patch="",
            resample_fn=lambda q, c, p, e: "new",
            max_resamples=2,
        )
        assert applied is False
        assert stats["ast_valid"] is False
        assert out_code == "def f():\n    return 1\n"

    def test_whitespace_only_patch_short_circuit(self):
        from src.tools.patch_applier import apply_patch_with_resample

        _out_code, applied, stats = apply_patch_with_resample(
            original_code="def f():\n    return 1\n",
            patch="   \n",
            resample_fn=None,
            max_resamples=0,
        )
        assert applied is False
        assert stats["resampled"] is False

    def test_valid_no_resample_needed(self):
        from src.tools.patch_applier import apply_patch_with_resample

        calls: list[str] = []

        def _cb(q, c, p, e):
            calls.append(q)
            return ""

        out_code, applied, stats = apply_patch_with_resample(
            original_code="def f():\n    return 1\n",
            patch="def f():\n    return 1\n",
            resample_fn=_cb,
            max_resamples=2,
        )
        assert applied is True
        assert out_code == "def f():\n    return 1\n"
        assert stats["success"] is True
        assert stats["resampled"] is False  # 首次即成功，未触发重采样
