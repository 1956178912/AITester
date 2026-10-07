"""E2 迭代批（2026-10-07）修复锁定测试。

三缺陷修复的行为锁（预注册"恰好一次"迭代的重跑前置）：
1. recursion_limit 上界 16×MAX_ITERATIONS+8（E1 4×MAX+8 触顶 2/12、
   E2 8×MAX+8 仍触顶 16/174 的实测收敛）——workflow 断言已同步，此处
   锁公式语义防回退；
2. _fl_at_k gold diff 优先路径（R8 docstring 设计口径的实现对齐——
   原实现只认系统补丁 diff，synthetic 整文件替换口径下 0/174 结构性
   为空）；
3. mutation_detection_rate 的保守 None 口径（"生成测试在 gold fixed 上
   不全绿 → None"）系**设计**而非缺陷——本文件锁定该语义防未来误改
   为 0% 误报（SWE-Mutation 对齐，AN2 批口径）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.run_benchmark import _fl_at_k


def _make_task(instance_code: str, fixed_code: str) -> SimpleNamespace:
    """构造带 gold fixed 材料的最小 task（_gold_fixed_code 单文件口径）。"""
    return SimpleNamespace(
        task_id="synthetic__task_9999",
        instance_code=instance_code,
        metadata={"fixed": fixed_code, "test_cases": [], "source": "test"},
        repo_name="synthetic/test",
    )


BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"


def _focus(line: int) -> dict:
    return {"top_k": [{"line": line, "score": 1.0}]}


class TestFlAtKGoldDiffPath:
    """gold diff 优先路径（E2-iter 新增，对齐 R8 docstring 设计）。"""

    def test_gold_diff_hit_with_empty_patch(self) -> None:
        """修复失败任务（patch 空）此前恒 None；gold diff 路径下应可测。

        buggy 第 2 行（return a - b）是缺陷行，fl Top-1 命中 → fl_at_1=1.0。
        """
        task = _make_task(BUGGY, FIXED)
        state = {"fl_spectral_focus": _focus(2), "patch": ""}
        result = _fl_at_k(state, task)
        assert result is not None
        assert result["fl_at_1"] == 1.0
        assert result["fl_at_3"] == 1.0
        assert result["fl_at_5"] == 1.0

    def test_gold_diff_miss(self) -> None:
        """Top-k 全不落在缺陷行 → 命中 0.0（可测但未命中，非 None）。"""
        task = _make_task(BUGGY, FIXED)
        state = {"fl_spectral_focus": _focus(99), "patch": ""}
        result = _fl_at_k(state, task)
        assert result is not None
        assert result["fl_at_1"] == 0.0

    def test_gold_diff_rejects_none_valued_hits(self) -> None:
        """top_k 行号为 None 的病态 focus 不应崩（排名元素缺 line 时跳过）。"""
        task = _make_task(BUGGY, FIXED)
        state = {"fl_spectral_focus": {"top_k": [{"score": 1.0}]}, "patch": ""}
        result = _fl_at_k(state, task)
        # ranked_lines=[None]，与 defect 行求交前 set 化——None 不命中即 0.0
        assert result is not None
        assert result["fl_at_1"] == 0.0


class TestFlAtKFallbackPath:
    """fallback：无 gold 时沿用系统补丁 diff（历史口径零变化）。"""

    def test_fallback_patch_diff(self) -> None:
        task = _make_task(BUGGY, "")  # 无 gold fixed
        unified = "--- a/mod.py\n+++ b/mod.py\n@@ -1,2 +1,2 @@\n-def add(a, b):\n-    return a - b\n+def add(a, b):\n+    return a + b\n"
        state = {"fl_spectral_focus": _focus(2), "patch": unified}
        result = _fl_at_k(state, task)
        assert result is not None
        assert result["fl_at_1"] == 1.0

    def test_both_paths_empty_returns_none(self) -> None:
        """无 gold、补丁非 diff 格式（整文件替换）→ None（历史口径）。"""
        task = _make_task(BUGGY, "")
        state = {"fl_spectral_focus": _focus(2), "patch": "python\ndef add(a, b):\n    return a + b\n"}
        assert _fl_at_k(state, task) is None

    def test_no_focus_returns_none(self) -> None:
        """无 fl_spectral_focus（无 debugger 路径 / 测量降级）→ None。"""
        task = _make_task(BUGGY, FIXED)
        assert _fl_at_k({"patch": ""}, task) is None
        assert _fl_at_k(None, task) is None


class TestRecursionLimitFormula:
    """recursion_limit 上界公式锁（E1/E2 双实证收敛值）。"""

    def test_formula_is_16x_plus_8(self) -> None:
        """MAX_ITERATIONS=3 → 56；防失控语义由内部轮次上限承担。"""
        import re

        src = (Path(__file__).resolve().parents[1] / "src" / "graph" / "workflow.py").read_text(encoding="utf-8")
        m = re.search(r"return _RecursionLimitedGraph\(_base_graph, (\d+) \* int\(MAX_ITERATIONS\) \+ (\d+)", src)
        assert m, "上界公式行未找到——公式被移动时同步本锁"
        assert (int(m.group(1)), int(m.group(2))) == (16, 8)


class TestMutationConservativeNone:
    """mutation_detection_rate 保守 None 口径锁（防误改为 0% 误报）。"""

    def test_skip_comment_present_in_source(self) -> None:
        """ "测试在 fixed 上不绿 → None"的保守语义须保留（SWE-Mutation 对齐）。"""
        src = (Path(__file__).resolve().parents[1] / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        assert "保守不误报 0" in src
