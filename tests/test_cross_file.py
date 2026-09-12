"""
src/tools/cross_file.py 单元测试（3.5 跨文件修复能力）。

覆盖：
- cross_file_enabled / cross_file_max_modules 环境变量开关
- analyze_cross_file_deps 的 AST 依赖识别（from X import Y / import X）
- _find_call_line 的调用行定位
- build_cross_file_repair_plan 的协调器-提议者流程
- apply_multi_file_patch 的多文件补丁应用（成功 / 部分失败回滚）
- cross_file_fallback_single_file 的降级路径
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.cross_file import (
    CrossFileDependency,
    CrossFileRepairPlan,
    _find_call_line,
    analyze_cross_file_deps,
    apply_multi_file_patch,
    build_cross_file_repair_plan,
    cross_file_enabled,
    cross_file_fallback_single_file,
    cross_file_max_modules,
)


class TestCrossFileSwitch:
    """3.5 跨文件修复开关与配置。"""

    def test_cross_file_enabled_default_false(self):
        """默认关闭（未设环境变量时）。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CROSS_FILE_ENABLE", None)
            assert cross_file_enabled() is False

    def test_cross_file_enabled_true(self):
        with patch.dict(os.environ, {"CROSS_FILE_ENABLE": "true"}):
            assert cross_file_enabled() is True

    def test_cross_file_enabled_case_insensitive(self):
        with patch.dict(os.environ, {"CROSS_FILE_ENABLE": "TRUE"}):
            assert cross_file_enabled() is True

    def test_cross_file_max_modules_default(self):
        """未设环境变量时返回默认值 5。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CROSS_FILE_MAX_MODULES", None)
            assert cross_file_max_modules() == 5

    def test_cross_file_max_modules_custom(self):
        with patch.dict(os.environ, {"CROSS_FILE_MAX_MODULES": "8"}):
            assert cross_file_max_modules() == 8

    def test_cross_file_max_modules_invalid_value(self):
        """非法值（非数字 / 0 / 负数）时回退默认值。"""
        for bad in ("abc", "0", "-3", ""):
            with patch.dict(os.environ, {"CROSS_FILE_MAX_MODULES": bad}):
                assert cross_file_max_modules() == 5


class TestAnalyzeCrossFileDeps:
    """3.5 AST 跨文件依赖分析。"""

    def test_from_import_detects_dep(self):
        """from X import Y 且 X 在项目内时识别为跨文件依赖。"""
        source_files = {
            "calculator": "def add(a, b):\n    return a + b\n",
            "user": "from calculator import add\n\ndef use():\n    return add(1, 2)\n",
        }
        deps = analyze_cross_file_deps("user", source_files)
        assert len(deps) == 1
        d = deps[0]
        assert d.source_module == "user"
        assert d.target_module == "calculator"
        assert d.symbol == "add"
        assert d.call_line > 0

    def test_import_statement_detects_dep(self):
        """import X 且 X 在项目内时识别为跨文件依赖。"""
        source_files = {
            "math_utils": "def sqrt(x):\n    return x ** 0.5\n",
            "main": "import math_utils\n\ndef run():\n    return math_utils.sqrt(4)\n",
        }
        deps = analyze_cross_file_deps("main", source_files)
        assert len(deps) == 1
        assert deps[0].target_module == "math_utils"
        assert deps[0].symbol == "math_utils"

    def test_external_module_not_included(self):
        """import 外部模块（不在 source_files 中）时不计入依赖。"""
        source_files = {
            "main": "import os\nimport sys\n\ndef run():\n    pass\n",
        }
        deps = analyze_cross_file_deps("main", source_files)
        assert deps == []

    def test_entry_module_not_in_source_files(self):
        """入口模块不在 source_files 时返回空。"""
        deps = analyze_cross_file_deps("nonexistent", {"other": "def f(): pass"})
        assert deps == []

    def test_syntax_error_entry_returns_empty(self):
        """入口模块语法错误时保守返回空（不抛异常）。"""
        deps = analyze_cross_file_deps("bad", {"bad": "def f(:\n"})
        assert deps == []

    def test_multiple_imports_from_same_module(self):
        """from X import Y, Z 时记录两条依赖边。"""
        source_files = {
            "lib": "def a():\n    pass\n\ndef b():\n    pass\n",
            "caller": "from lib import a, b\n",
        }
        deps = analyze_cross_file_deps("caller", source_files)
        symbols = {d.symbol for d in deps}
        assert symbols == {"a", "b"}
        assert all(d.target_module == "lib" for d in deps)

    def test_dedup_same_edge(self):
        """重复 import 语句时去重（同一 source/target/symbol 只保留一条）。"""
        source_files = {
            "lib": "def f():\n    pass\n",
            "caller": "from lib import f\nfrom lib import f\n",
        }
        deps = analyze_cross_file_deps("caller", source_files)
        assert len(deps) == 1


class TestFindCallLine:
    """_find_call_line 调用行定位。"""

    def test_find_simple_call(self):
        lines = ["def run():", "    x = compute(1)", "    return x"]
        assert _find_call_line(lines, "compute") == 2

    def test_find_no_call(self):
        lines = ["def run():", "    pass"]
        assert _find_call_line(lines, "compute") == 0

    def test_find_symbol_with_word_boundary(self):
        """符号带词边界：'compute' 不应匹配 'xcompute('。"""
        lines = ["def run():", "    xcompute(1)"]
        assert _find_call_line(lines, "compute") == 0


class TestBuildCrossFileRepairPlan:
    """3.5 协调器-提议者：多文件修复计划构建。"""

    def _mock_debugger(self, patch_text: str = "def f():\n    return 42\n"):
        from unittest.mock import MagicMock

        debugger = MagicMock()
        debugger.debug.return_value = {
            "root_cause": "bug",
            "error_category": "logic",
            "fix_strategy": "fix",
            "patch": patch_text,
        }
        return debugger

    def test_plan_includes_all_modules(self):
        """依赖图中的所有模块都进入 target_modules（去重排序）。"""
        deps = [
            CrossFileDependency("caller", "lib", "f", call_line=1),
            CrossFileDependency("caller", "other", "g", call_line=2),
        ]
        plan = build_cross_file_repair_plan(
            deps,
            self._mock_debugger(),
            target_code="def caller(): pass",
            test_output="",
            failed_cases=[],
        )
        assert set(plan.target_modules) == {"caller", "lib", "other"}
        assert len(plan.target_modules) == 3
        assert len(plan.per_module_patches) == 3
        assert plan.dependency_edges == deps

    def test_plan_respects_max_modules(self):
        """超过 max_modules 时截断到前 N 个（按字典序）。"""
        deps = [CrossFileDependency("caller", f"m{i}", "f", call_line=i + 1) for i in range(10)]
        plan = build_cross_file_repair_plan(
            deps,
            self._mock_debugger(),
            target_code="def caller(): pass",
            test_output="",
            failed_cases=[],
            max_modules=3,
        )
        assert len(plan.target_modules) <= 3
        assert "caller" in plan.target_modules

    def test_plan_handles_debugger_failure(self):
        """提议者（debugger.debug）抛异常时，该模块跳过（不写入 patches）。"""
        from unittest.mock import MagicMock

        deps = [CrossFileDependency("caller", "lib", "f", call_line=1)]
        debugger = MagicMock()
        debugger.debug.side_effect = RuntimeError("LLM 调用失败")
        plan = build_cross_file_repair_plan(
            deps,
            debugger,
            target_code="def caller(): pass",
            test_output="",
            failed_cases=[],
        )
        # 失败的模块不写入 per_module_patches
        assert "lib" not in plan.per_module_patches

    def test_plan_estimates_token_cost(self):
        """token 成本按字符数 / 4 保守估算。"""
        deps = [CrossFileDependency("caller", "lib", "f", call_line=1)]
        patch_text = "x" * 400  # 400 字符 → 预估 100 token
        plan = build_cross_file_repair_plan(
            deps,
            self._mock_debugger(patch_text),
            target_code="def c(): pass",
            test_output="",
            failed_cases=[],
        )
        assert plan.estimated_token_cost >= 100


class TestApplyMultiFilePatch:
    """3.5 多文件补丁应用。"""

    def test_success(self):
        """多文件补丁全部成功。"""
        original_files = {
            "lib": "def f():\n    return 1\n",
            "caller": "def c():\n    import lib\n    return lib.f()\n",
        }
        patches = {
            "lib": "def f():\n    return 2\n",
        }
        new_files, ok = apply_multi_file_patch(original_files, patches, "caller")
        assert ok is True
        assert "return 2" in new_files["lib"]
        assert "caller" in new_files

    def test_empty_patches_noop(self):
        """无补丁时返回原文件映射 + True。"""
        original_files = {"a": "def a(): pass"}
        new_files, ok = apply_multi_file_patch(original_files, {}, "a")
        assert ok is True
        assert new_files == original_files

    def test_module_not_in_original_skipped(self):
        """补丁目标模块不在 original_files 时跳过该模块（不阻断其他）。"""
        original_files = {"lib": "def f():\n    return 1\n"}
        patches = {"nonexistent": "def g(): pass"}
        new_files, ok = apply_multi_file_patch(original_files, patches, "lib")
        assert ok is True  # 跳过的不算失败
        assert "nonexistent" not in new_files

    def test_apply_failure_rolls_back(self):
        """单文件补丁应用失败时整体回滚（保守口径）。"""
        original_files = {
            "lib": "def f():\n    return 1\n",
        }
        # 补丁试图替换不存在的函数 → apply_patch_to_code 失败
        patches = {"lib": "def nonexistent():\n    pass\n"}
        new_files, ok = apply_multi_file_patch(original_files, patches, "lib")
        assert ok is False
        # 回滚到原始代码
        assert new_files["lib"] == original_files["lib"]


class TestCrossFileFallbackSingleFile:
    """3.5 降级单文件路径。"""

    def test_entry_module_no_patch_returns_unchanged(self):
        """入口模块无补丁时保持原样。"""
        original_files = {"lib": "def f():\n    return 1\n"}
        new_files, ok = cross_file_fallback_single_file(original_files, {}, "lib")
        assert ok is True
        assert new_files == original_files

    def test_entry_module_patch_applied(self):
        """入口模块有补丁时应用。"""
        original_files = {"lib": "def f():\n    return 1\n"}
        patches = {"lib": "def f():\n    return 2\n"}
        new_files, ok = cross_file_fallback_single_file(original_files, patches, "lib")
        assert ok is True
        assert "return 2" in new_files["lib"]


class TestCrossFileRepairPlanSerialization:
    """CrossFileRepairPlan.to_dict 可 JSON 化（供 workflow state / trace 使用）。"""

    def test_to_dict_roundtrip(self):
        deps = [CrossFileDependency("a", "b", "f", call_line=5, context="ctx")]
        plan = CrossFileRepairPlan(
            plan_id="p1",
            target_modules=["a", "b"],
            per_module_patches={"a": "def a(): pass"},
            dependency_edges=deps,
            estimated_token_cost=42,
        )
        d = plan.to_dict()
        assert d["plan_id"] == "p1"
        assert d["target_modules"] == ["a", "b"]
        assert d["per_module_patches"]["a"] == "def a(): pass"
        assert d["dependency_edges"][0]["symbol"] == "f"
        assert d["estimated_token_cost"] == 42
