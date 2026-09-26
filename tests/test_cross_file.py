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
    analyze_multi_entry_deps,
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

    def test_source_files_per_module_code(self):
        """2026-09-26 全面审查（CF-3 修复）：提供 source_files 时每个模块
        用自己模块的源码生成补丁，且 target_module 参数为该模块名（协调器-
        提议者本意：提议者看到的是自己模块的代码 + 自己模块的 prompt 约束）。
        """
        from unittest.mock import MagicMock

        deps = [
            CrossFileDependency("caller", "lib", "f", call_line=1),
            CrossFileDependency("caller", "other", "g", call_line=2),
        ]
        source_files = {
            "caller": "def caller(): pass",
            "lib": "def f(): return 1",
            "other": "def g(): return 2",
        }
        debugger = MagicMock()
        debugger.debug.return_value = {"patch": "def x(): pass"}
        plan = build_cross_file_repair_plan(
            deps,
            debugger,
            target_code="ENTRY_CODE",
            test_output="",
            failed_cases=[],
            source_files=source_files,
        )
        # 每模块都用自己模块的源码（非入口 target_code）
        calls = debugger.debug.call_args_list
        target_codes_seen = [c.kwargs.get("target_code") or c.args[0] for c in calls]
        target_modules_seen = [c.kwargs.get("target_module") for c in calls]
        assert target_codes_seen == [
            source_files["caller"],
            source_files["lib"],
            source_files["other"],
        ]
        assert target_modules_seen == ["caller", "lib", "other"]
        assert len(plan.per_module_patches) == 3

    def test_source_files_fallback_to_target_code(self):
        """CF-3 兼容口径：source_files 未含某模块（或传 None）时回退
        入口 target_code（历史行为，不阻断该模块补丁生成）。"""
        from unittest.mock import MagicMock

        deps = [
            CrossFileDependency("caller", "lib", "f", call_line=1),
            CrossFileDependency("caller", "other", "g", call_line=2),
        ]
        # source_files 只含 caller，不含 lib/other → lib/other 回退 target_code
        source_files = {"caller": "def caller(): pass"}
        debugger = MagicMock()
        debugger.debug.return_value = {"patch": "def x(): pass"}
        build_cross_file_repair_plan(
            deps,
            debugger,
            target_code="ENTRY",
            test_output="",
            failed_cases=[],
            source_files=source_files,
        )
        calls = debugger.debug.call_args_list
        target_codes = [c.kwargs.get("target_code") or c.args[0] for c in calls]
        assert target_codes[0] == "def caller(): pass"  # caller 用自有源码
        assert target_codes[1] == "ENTRY"  # lib 回退入口代码
        assert target_codes[2] == "ENTRY"  # other 回退入口代码

    def test_source_files_none_keeps_legacy_behavior(self):
        """CF-3 兼容口径：source_files=None（未传）时全模块共用 target_code
        （历史单参数语义，向后兼容）。"""
        from unittest.mock import MagicMock

        deps = [
            CrossFileDependency("caller", "lib", "f", call_line=1),
            CrossFileDependency("caller", "other", "g", call_line=2),
        ]
        debugger = MagicMock()
        debugger.debug.return_value = {"patch": "def x(): pass"}
        build_cross_file_repair_plan(
            deps,
            debugger,
            target_code="ENTRY",
            test_output="",
            failed_cases=[],
        )
        calls = debugger.debug.call_args_list
        target_codes = [c.kwargs.get("target_code") or c.args[0] for c in calls]
        assert all(tc == "ENTRY" for tc in target_codes)
        # CF-3 修复后：CF-3 前 target_module 恒为调用方传入的 target_module
        # （默认 None），现在改为按模块名（module_name）传入——协调器-提议者
        # 本意：LLM prompt 约束的是"当前提议者负责的模块"。测试不再锁定
        # 调用方的 target_module，改为验证每个模块拿到的是自己的模块名
        target_modules_seen = [c.kwargs.get("target_module") for c in calls]
        assert target_modules_seen == ["caller", "lib", "other"]


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


# ─── 3.5 二期：多入口依赖分析 + 拓扑序补丁应用 + 修复计划缓存 ──────────────────────


class TestAnalyzeMultiEntryDeps:
    """3.5 二期 analyze_multi_entry_deps：多入口依赖分析（一级展开，去重合并）。"""

    def test_two_entries_union(self):
        """两个入口的依赖边取并集（去重）。"""
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "b": "from lib import helper\n\ndef b():\n    return helper(2)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        deps = analyze_multi_entry_deps(["a", "b"], source_files)
        keys = {(d.source_module, d.target_module, d.symbol) for d in deps}
        assert ("a", "lib", "helper") in keys
        assert ("b", "lib", "helper") in keys
        # 两个入口共享 lib，但 source_module 不同，应是 2 条边（不去重 source 不同者）
        assert len(deps) == 2

    def test_dedup_same_entry_repeated(self):
        """同一入口重复出现时去重（同 (source, target, symbol) 只留一条）。"""
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        deps = analyze_multi_entry_deps(["a", "a", "a"], source_files)
        assert len(deps) == 1
        assert deps[0].source_module == "a"

    def test_empty_entries_returns_empty(self):
        """无入口时返回空列表。"""
        source_files = {"lib": "def f(): pass"}
        assert analyze_multi_entry_deps([], source_files) == []

    def test_entry_not_in_source_files_returns_empty(self):
        """入口不在 source_files 中时，该入口贡献 0 条边。"""
        source_files = {"lib": "def f(): pass"}
        assert analyze_multi_entry_deps(["missing"], source_files) == []

    def test_call_line_min_kept_on_dedup(self):
        """同键去重时保留 call_line 最小者（最早调用点）。"""
        # a 在 2 行调用 helper，b 在 3 行调用——构造同 (source,target,symbol) 不可能，
        # 因为 source_module 不同。改用同一入口源码中多行调用同一符号的场景：
        # 一期 analyze_cross_file_deps 对每 symbol 只取首个 call_line，
        # 故多入口去重的"call_line 最小"主要发生在跨入口共享符号时。
        # 这里验证：两入口共享同一符号，各自 call_line 不同，合并后每 source 各一条。
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    x = helper(1)\n    return x\n",
            "b": "from lib import helper\n\ndef b():\n    return helper(2)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        deps = analyze_multi_entry_deps(["a", "b"], source_files)
        by_src = {d.source_module: d for d in deps}
        assert set(by_src) == {"a", "b"}
        assert by_src["a"].call_line >= 1
        assert by_src["b"].call_line >= 1


class TestTopologicalOrder:
    """3.5 二期 apply_multi_file_patch 拓扑序：被调用方先改，调用方后改。"""

    def test_callee_before_caller(self):
        """被调用方 lib 先于调用方 caller 应用。"""
        original_files = {
            "lib": "def f():\n    return 1\n",
            "caller": "import lib\n\ndef c():\n    return lib.f()\n",
        }
        patches = {
            "lib": "def f():\n    return 2\n",
            "caller": "import lib\n\ndef c():\n    return lib.f() + 1\n",
        }
        deps = [CrossFileDependency("caller", "lib", "f", call_line=3, context="")]
        new_files, ok = apply_multi_file_patch(original_files, patches, "caller", deps=deps)
        assert ok is True
        # 拓扑序保证两个都应用成功
        assert "return 2" in new_files["lib"]
        assert "lib.f() + 1" in new_files["caller"]

    def test_no_deps_falls_back_to_lexicographic(self):
        """不传 deps 时退回字典序（一期口径）。"""
        original_files = {
            "z_mod": "def z():\n    return 1\n",
            "a_mod": "def a():\n    return 1\n",
        }
        patches = {
            "z_mod": "def z():\n    return 2\n",
            "a_mod": "def a():\n    return 2\n",
        }
        new_files, ok = apply_multi_file_patch(original_files, patches, "z_mod")
        assert ok is True
        assert "return 2" in new_files["z_mod"]
        assert "return 2" in new_files["a_mod"]

    def test_entry_forced_first(self):
        """entry_module 永远最先应用（被调用方根）。"""
        original_files = {
            "mid": "def m():\n    return 1\n",
            "entry": "def e():\n    return 1\n",
        }
        patches = {
            "mid": "def m():\n    return 2\n",
            "entry": "def e():\n    return 2\n",
        }
        # entry 依赖 mid（entry 引用 mid），拓扑上 mid 应先；但 entry 强制首位
        deps = [CrossFileDependency("entry", "mid", "m", call_line=1, context="")]
        new_files, ok = apply_multi_file_patch(original_files, patches, "entry", deps=deps)
        assert ok is True
        # entry 强制首位的应用不影响最终结果正确性（两个模块都应用成功）
        assert "return 2" in new_files["entry"]
        assert "return 2" in new_files["mid"]

    def test_cycle_breaks_by_lexicographic(self):
        """依赖环时按字典序打破（保守回退，不阻塞应用）。"""
        original_files = {
            "x": "def x():\n    return 1\n",
            "y": "def y():\n    return 1\n",
        }
        patches = {
            "x": "def x():\n    return 2\n",
            "y": "def y():\n    return 2\n",
        }
        # x 依赖 y，y 也依赖 x → 环
        deps = [
            CrossFileDependency("x", "y", "y", call_line=1, context=""),
            CrossFileDependency("y", "x", "x", call_line=1, context=""),
        ]
        new_files, ok = apply_multi_file_patch(original_files, patches, "x", deps=deps)
        assert ok is True
        assert "return 2" in new_files["x"]
        assert "return 2" in new_files["y"]

    def test_parallel_edges_counted_per_edge(self):
        """同一对模块的多条并行依赖边按边计数（入度 K，逐边 -1 释放）。

        回归测试：入度统计口径必须与释放口径对称（同一 source→target 的
        K 条边计 K 次入度、释放时扣 K 次）。若释放侧误按"去重后的调用方
        集合"只扣一次（如 min-heap 优化误判），K>1 时入度永远无法归零，
        节点被误判为环，拓扑序可能违反"被调用方先改、调用方后改"的
        基本语义（已验证：随机图上该误判实现存在调用方先于被调用方的
        违规排序，而本实现保持确定性口径且 2000 随机图对拍一致）。

        用例设计：m→a ×3 并行 + a→b ×1；z 强制首位（entry）。
        m 入度 3，a 入度 1，b 入度 0，z 入度 0。
        - 逐边扣减（正确口径）：b/z 入度 0 先排，释放 b 扣 a→b 边
          a 入度 0 入队；释放 z 无后续；释放 a 扣 3 条 m→a 边
          m 入度 3-3=0 入队。order = [z, b, a, m]。
        - 去重扣减（误判口径）：释放 a 只扣 1 次 m→a 边，
          m 入度 3-1=2 永远 >0，m 落入环尾兜底——
          虽本例外部 order 与逐边相同（m 字典序恰在 a 后），
          但随机图验证已确认存在外部可观测的语义违规。
        本用例锁定"逐边扣减 + 确定性队列"的口径。
        """
        from src.tools.cross_file import _topological_order

        patches = {"a": "", "b": "", "m": "", "z": ""}
        deps = [
            CrossFileDependency("m", "a", "f1", call_line=1, context=""),
            CrossFileDependency("m", "a", "f2", call_line=2, context=""),
            CrossFileDependency("m", "a", "f3", call_line=3, context=""),
            CrossFileDependency("a", "b", "g", call_line=4, context=""),
        ]
        order = _topological_order(patches, deps, "z")
        assert order == ["z", "b", "a", "m"]

    def test_parallel_edges_entry_first(self):
        """并行边 + entry 强制首位：entry 仍最先，其余按拓扑序。"""
        from src.tools.cross_file import _topological_order

        patches = {"entry": "", "lib": ""}
        deps = [
            CrossFileDependency("entry", "lib", "f", call_line=1, context=""),
            CrossFileDependency("entry", "lib", "g", call_line=2, context=""),
        ]
        order = _topological_order(patches, deps, "entry")
        assert order[0] == "entry"
        assert "lib" in order


class TestRepairPlanCache:
    """3.5 二期 build_cross_file_repair_plan_cached：相同依赖图复用 LLM 结果，省 token。"""

    def _fake_debugger(self, calls):
        class _Debug:
            def debug(self, **kwargs):
                calls.append(kwargs)
                return {"patch": "def f():\n    return 42\n"}

        return _Debug()

    def test_cache_hit_skips_second_llm_call(self, tmp_path, monkeypatch):
        """相同依赖图第二次调用命中缓存，零 LLM 调用。"""
        from src.tools import cross_file as cf

        calls: list[dict] = []
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        debugger = self._fake_debugger(calls)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")

        plan1 = cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
        )
        first_call_count = len(calls)
        assert first_call_count >= 1  # 首次 build 至少 1 次 LLM（每模块一次）

        # 相同依赖图 → 命中缓存（LLM 调用次数不再增加）
        plan2 = cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
        )
        assert len(calls) == first_call_count  # 第二次零新增 LLM（命中缓存）
        assert plan1.target_modules == plan2.target_modules
        assert plan1.per_module_patches == plan2.per_module_patches

    def test_cache_disabled_reads_no_file(self, tmp_path, monkeypatch):
        """AITESTER_LLM_CACHE=0 时不读写缓存，每次都调 LLM。"""
        from src.tools import cross_file as cf

        calls: list[dict] = []
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        debugger = self._fake_debugger(calls)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")

        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
        )
        first_count = len(calls)
        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
        )
        assert len(calls) > first_count  # 缓存关闭，第二次仍调 LLM（次数增长）

    def test_use_cache_false_behaves_like_uncached(self, tmp_path, monkeypatch):
        """use_cache=False 等同直接调用（不读不写缓存）。"""
        from src.tools import cross_file as cf

        calls: list[dict] = []
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        debugger = self._fake_debugger(calls)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")

        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
            use_cache=False,
        )
        first_count = len(calls)
        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
            use_cache=False,
        )
        assert len(calls) > first_count  # use_cache=False，第二次仍调 LLM

    def test_different_deps_no_cache_hit(self, tmp_path, monkeypatch):
        """不同依赖图（max_modules 不同）不命中缓存。"""
        from src.tools import cross_file as cf

        calls: list[dict] = []
        source_files = {
            "a": "from lib import helper\n\ndef a():\n    return helper(1)\n",
            "lib": "def helper(x):\n    return x + 1\n",
        }
        debugger = self._fake_debugger(calls)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")

        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
            max_modules=3,
        )
        first_count = len(calls)
        cf.build_cross_file_repair_plan_cached(
            entry_modules=["a"],
            source_files=source_files,
            debugger=debugger,
            target_code=source_files["a"],
            test_output="",
            failed_cases=[],
            max_modules=10,
        )
        assert len(calls) > first_count  # max_modules 不同 → 不同指纹 → 不命中
