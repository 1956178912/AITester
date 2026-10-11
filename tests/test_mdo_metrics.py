"""MDO（政策无关变异判别力度量）回归守卫。

对应外部评审 §3.4 提出的核心缺陷：`detection_rate` 与修复策略数学耦合，导致
"测试生成质量"无法与"修复策略"分离度量。MDO 以**行为差异 + 断言结果**为判据、
不涉及任何补丁动作，从而做到政策无关。

本文件锁定四条不变量：
1. **MDR 必须能区分弱断言与强断言**（既有 `mutation_score` 无法区分——实测两者都得 1.0）；
2. **CRASH 不得并入 MDR**（崩溃型变异体不是断言判别力）；
3. **不可测语义 fail-closed**（未全绿 / 空池 / 基准不可跑 → available=False + 原因，不臆造 0）；
4. **池规模下限的定量公式**（n ≥ ln(α)/ln(1−p)），并在未达下限时显式置位。

纪律：零 LLM；全部为子进程执行真实 pytest，不 mock。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.measurement.mdo import (
    POOL_FLOOR_FOR_5PCT,
    POOL_FLOOR_FOR_10PCT,
    compute_mdo,
    pool_floor,
)

_BASE = "def f(x):\n    if x > 0:\n        return x + 1\n    return 0\n"
_WEAK = "from t import f\n\ndef test_f():\n    assert isinstance(f(1), int)\n"
_STRONG = "from t import f\n\ndef test_f():\n    assert f(1) == 2\n    assert f(-5) == 0\n    assert f(0) == 0\n"
_NEVER_GREEN = "from t import f\n\ndef test_f():\n    assert f(1) == 999\n"


class _M:
    """最小变异体替身。"""

    def __init__(self, code: str, mutant_type: str = "probe", desc: str = "") -> None:
        self.code = code
        self.mutant_type = mutant_type
        self.description = desc or mutant_type
        self.line_no = 1


class TestPoolFloor:
    """池规模下限的定量依据（模块 docstring 的公式）。"""

    @pytest.mark.parametrize(
        ("p", "expected"),
        [(0.10, 29), (0.05, 59), (0.20, 14)],
    )
    def test_floor_matches_closed_form(self, p: float, expected: int) -> None:
        assert pool_floor(p) == expected

    def test_named_constants_agree_with_formula(self) -> None:
        assert POOL_FLOOR_FOR_10PCT == pool_floor(0.10) == 29
        assert POOL_FLOOR_FOR_5PCT == pool_floor(0.05) == 59

    @pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 2.0])
    def test_invalid_p_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError):
            pool_floor(bad)


class TestMDOFailClosed:
    """不可测语义：必须给出原因，不得臆造 0。"""

    def test_empty_pool(self) -> None:
        r = compute_mdo(base_code=_BASE, test_code=_STRONG, module_name="t", mutants=[])
        assert r.available is False
        assert r.not_available_reason == "empty_mutant_pool"
        assert r.mutant_discrimination_rate is None

    def test_test_not_green_on_base(self) -> None:
        r = compute_mdo(
            base_code=_BASE,
            test_code=_NEVER_GREEN,
            module_name="t",
            mutants=[_M("def f(x):\n    return 0\n")],
        )
        assert r.available is False
        assert r.not_available_reason.startswith("test_not_green_on_base")
        assert r.mutant_discrimination_rate is None

    def test_no_test_code(self) -> None:
        r = compute_mdo(base_code=_BASE, test_code="", module_name="t", mutants=[_M("x=1")])
        assert r.available is False
        assert r.not_available_reason == "no_test_code"

    def test_no_base_code(self) -> None:
        r = compute_mdo(base_code="", test_code=_STRONG, module_name="t", mutants=[_M("x=1")])
        assert r.available is False
        assert r.not_available_reason == "no_base_code"


class TestMDODiscrimination:
    """核心断言：MDR 能区分弱/强断言（这是本指标存在的理由）。"""

    # 两个变异体：一个改变返回值（应被强断言判别），一个只改 return None 分支
    _MUTANTS: ClassVar[list[_M]] = [
        _M("def f(x):\n    if x > 0:\n        return x + 2\n    return 0\n", "numeric_offset"),
        _M("def f(x):\n    if x > 0:\n        return x + 1\n    return None\n", "return_void"),
    ]

    def test_weak_assertion_triggers_but_does_not_discriminate(self) -> None:
        r = compute_mdo(base_code=_BASE, test_code=_WEAK, module_name="t", mutants=self._MUTANTS)
        assert r.available is True
        # 弱断言（只查类型）会让行为偏差发生，但捕获不到
        assert r.mutant_trigger_rate == 1.0, "两个变异体都改变了行为 → 触发率应为 1.0"
        assert r.mutant_discrimination_rate == 0.0, "弱断言不应判别出任何变异体"
        assert r.crash_rate == 0.0

    def test_strong_assertion_discriminates(self) -> None:
        r = compute_mdo(base_code=_BASE, test_code=_STRONG, module_name="t", mutants=self._MUTANTS)
        assert r.available is True
        assert r.mutant_trigger_rate == 1.0
        assert r.mutant_discrimination_rate == 1.0, "强断言应判别两个变异体"

    def test_mdr_strictly_below_mtr_for_weak_suite(self) -> None:
        """MTR 与 MDR 必须是可分离的两个量（否则与旧 mutation_score 无区别）。"""
        weak = compute_mdo(base_code=_BASE, test_code=_WEAK, module_name="t", mutants=self._MUTANTS)
        assert weak.mutant_trigger_rate is not None and weak.mutant_discrimination_rate is not None
        assert weak.mutant_discrimination_rate < weak.mutant_trigger_rate


class TestCrashNotCountedAsDiscrimination:
    """崩溃型变异体必须计入 CRASH，绝不计入 MDR。"""

    def test_syntax_error_mutant_is_crash_not_discrimination(self) -> None:
        broken = _M("def f(x)\n    return 1\n", "syntax_break")  # 语法错误
        r = compute_mdo(base_code=_BASE, test_code=_STRONG, module_name="t", mutants=[broken])
        assert r.available is True
        assert r.crash_rate == 1.0, "语法错误变异体应记为崩溃"
        assert r.mutant_discrimination_rate == 0.0, "崩溃不得计入判别率"

    def test_pool_floor_flag_marks_insufficient_pool(self) -> None:
        """池过小必须显式置位（防止在饱和指标上做结论）。"""
        r = compute_mdo(
            base_code=_BASE,
            test_code=_STRONG,
            module_name="t",
            mutants=[_M("def f(x):\n    return 0\n")],
        )
        assert r.pool_size == 1
        assert r.pool_floor_ok is False

    def test_as_dict_is_json_serializable(self) -> None:
        import json

        r = compute_mdo(base_code=_BASE, test_code=_STRONG, module_name="t", mutants=[_M("x=1")])
        payload = r.as_dict()
        # 显式断言（门禁 check_zero_assert_tests 要求有效断言信号；此前仅
        # "调用不抛异常"，语义上等于零断言）：既要可序列化，也要是 dict，
        # 且 T6 的审计字段必须是纯 dict（可喂给下游 JSON 写入）。
        dumped = json.dumps(payload)
        assert isinstance(payload, dict), "as_dict 必须返回 dict"
        assert isinstance(json.loads(dumped), dict), "序列化往返必须保持 dict"
        if payload.get("mdo_provisional"):
            assert isinstance(payload.get("mdo_raw"), dict), "provisional 时 mdo_raw 必须是纯 dict"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


class TestExtendedMutantPool:
    """扩展算子集：提升池规模，且**不改变基类历史口径**。"""

    _CODE = (
        "def g(items, limit):\n"
        "    total = 0\n"
        "    for it in items:\n"
        "        if it > limit and it != 0:\n"
        "            total += it * 2\n"
        "        elif not it:\n"
        "            total -= 1\n"
        "    return total\n"
    )

    def test_extended_pool_is_larger_than_base(self) -> None:
        from experiments.mutation_testing import ExtendedMutationGenerator, MutationGenerator

        base = MutationGenerator().generate(self._CODE)
        ext = ExtendedMutationGenerator().generate(self._CODE)
        assert len(ext) > len(base), "扩展算子集必须提升池规模（否则无法解除饱和）"

    def test_extended_pool_covers_more_types(self) -> None:
        from experiments.mutation_testing import ExtendedMutationGenerator, MutationGenerator

        tb = {m.mutant_type for m in MutationGenerator().generate(self._CODE)}
        te = {m.mutant_type for m in ExtendedMutationGenerator().generate(self._CODE)}
        assert te > tb, "扩展算子集必须覆盖更多变异类型"
        assert {"arith_op_swap", "aug_assign_swap", "bool_op_swap", "cond_negate"} <= te

    def test_base_generator_unchanged(self) -> None:
        """口径不变性：新增算子不得改变基类输出（历史批次可比性）。"""
        from experiments.mutation_testing import MutationGenerator

        pool = MutationGenerator().generate(self._CODE)
        assert len(pool) <= 20, "基类上限仍为 20（历史口径）"
        assert MutationGenerator._MAX_MUTANTS_PER_TASK == 20

    def test_extended_respects_max_per_task(self) -> None:
        from experiments.mutation_testing import ExtendedMutationGenerator

        pool = ExtendedMutationGenerator(max_per_task=3).generate(self._CODE)
        assert len(pool) <= 3

    def test_pool_floor_is_unreachable_for_small_functions(self) -> None:
        """定量事实（写进结论，避免把"池不足"误读为"指标失效"）：

        池下限 29 需要 ≥29 个**可变异单点**。21 条语句的函数不可能达到——
        因此在小函数上正确做法是**如实报 pool_floor_ok=False**，而不是
        在饱和指标上出结论。
        """
        from experiments.mutation_testing import ExtendedMutationGenerator

        ext = ExtendedMutationGenerator().generate(self._CODE)
        assert len(ext) < POOL_FLOOR_FOR_10PCT, (
            "本用例故意断言'小函数达不到下限'——若此断言失败说明算子集已足够大，应改为正向断言并更新优化方案 §3.4"
        )


class TestMDOResultRowSchema:
    """MDO 接入结果行的 schema 守卫（键集合同构 + 默认关零行为变化）。"""

    _MDO_KEYS = (
        "mdo_available",
        "mtr",
        "mdr",
        "mdo_crash_rate",
        "mdo_pool_size",
        "mdo_pool_floor_ok",
        "mdo_not_available_reason",
    )

    def test_build_task_result_declares_mdo_keys(self) -> None:
        """成功分支必须声明全部 MDO 键（默认 None），保证键集合同构。"""
        import inspect

        from experiments import run_benchmark as rb

        src = inspect.getsource(rb._build_task_result)
        for key in self._MDO_KEYS:
            assert f'"{key}"' in src, f"结果行缺少 MDO 键：{key}"

    def test_failure_branch_declares_mdo_keys(self) -> None:
        """失败分支同样声明（否则统计层键缺失）。"""
        import pathlib

        src = pathlib.Path("experiments/run_benchmark.py").read_text(encoding="utf-8")
        # 失败分支行字典：从 "coverage": 0.0 起到该字典闭合
        start = src.index('"coverage": 0.0,\n        "iterations": 0,')
        end = src.index("\n    }", start)
        block = src[start:end]
        for key in self._MDO_KEYS:
            assert f'"{key}"' in block, f"失败分支缺少 MDO 键：{key}"

    def test_wiring_is_gated_by_mutation_switch(self) -> None:
        """MDO 计算必须与 ENABLE_MUTATION_SCORING 同挂点（默认关零行为变化）。"""
        import pathlib

        src = pathlib.Path("experiments/run_benchmark.py").read_text(encoding="utf-8")
        idx_switch = src.index("mutation_enabled = ENABLE_MUTATION_SCORING")
        idx_mdo = src.index("_compute_mdo_for_baseline(bl_results, task_map)")
        idx_detect = src.index("_compute_mutation_detection_for_baseline(bl_results, task_map")
        assert idx_switch < idx_detect < idx_mdo, "MDO 必须在同一开关分支内且位于既有挂点之后"

    def test_no_llm_import_in_measurement_layer(self) -> None:
        """测量层必须零 LLM 依赖（政策无关的前提之一）。"""
        import pathlib

        src = pathlib.Path("src/measurement/mdo.py").read_text(encoding="utf-8")
        for banned in ("openai", "langchain", "BaseAgent", "llm_client"):
            assert banned not in src, f"MDO 不得依赖 LLM：出现 {banned}"


class TestMDOBaselineSemantics:
    """MDO 的基准必须是 **gold 修复后代码**（而非缺陷代码）——2026-10-11 修正。

    语义依据：MDO 度量"测试对**正确实现**的变异体是否具备判别力"，因此测试
    必须在基准上全绿。这与 M1 detection 的 F2P 第二段（buggy 红 ∧ gold 绿）
    同源，保证"红"是**缺陷特异**的。若误用缺陷代码作基准，测试本应红，
    MDO 会大面积记 `not_measurable`（实测 aitester 臂几乎全部不可测）。
    """

    _BUGGY = "def f(x):\n    return x - 1\n"
    _FIXED = "def f(x):\n    return x + 1\n"  # gold：f(1) == 2
    _TC = "from t import f\n\ndef test_f():\n    assert f(1) == 2\n"

    def _task(self, *, with_gold: bool = True) -> object:
        md: dict[str, object] = {"source": "synthetic", "test_cases": self._TC}
        if with_gold:
            md["fixed"] = self._FIXED

        class _T:
            task_id = "synthetic__t"
            instance_code = self._BUGGY
            metadata = md

        return _T()

    def test_uses_gold_fixed_as_baseline(self) -> None:
        """缺陷特异的测试（buggy 上红 / fixed 上绿）在 MDO 下应**可测**。"""
        from experiments.run_benchmark import _compute_mdo_for_baseline

        rows: list[dict[str, object]] = [
            {"task_id": "synthetic__t", "generated_test": self._TC},
        ]
        _compute_mdo_for_baseline(rows, {"synthetic__t": self._task()})
        assert rows[0]["mdo_available"] is True, (
            f"应可测（基准=gold fixed）；实际 reason={rows[0]['mdo_not_available_reason']!r}"
        )
        # T6（2026-10-11 独立评审落地）：本 fixture 只产出 2 个变异体
        # （ExtendedMutationGenerator → ['return_void','arith_op_swap']），
        # 远低于池规模下限 29 → pool_floor_ok=False → 规范出口 mtr/mdr
        # 必须为 None（防止下游把"小池满判别"误读为"判别力满分"）。
        # 原始计算值仍可在 mdo_raw 中审计。
        assert rows[0]["mdr"] is None, "池未达下限 → 规范出口不得给数字"
        assert rows[0]["mdo_pool_floor_ok"] is False
        assert rows[0]["mdo_raw"]["mdr"] is not None, "计算仍应发生，原始值可审计"

    def test_missing_gold_is_fail_closed(self) -> None:
        """无 gold 材料 → 不可测且给出原因（不得臆造 0）。"""
        from experiments.run_benchmark import _compute_mdo_for_baseline

        rows: list[dict[str, object]] = [
            {"task_id": "synthetic__t", "generated_test": self._TC},
        ]
        _compute_mdo_for_baseline(rows, {"synthetic__t": self._task(with_gold=False)})
        assert rows[0]["mdo_available"] is None
        assert rows[0]["mdo_not_available_reason"] == "no_gold_fixed_material"
        assert rows[0]["mdr"] is None

    def test_missing_task_or_test_is_none(self) -> None:
        from experiments.run_benchmark import _compute_mdo_for_baseline

        rows: list[dict[str, object]] = [
            {"task_id": "synthetic__absent", "generated_test": self._TC},
            {"task_id": "synthetic__t", "generated_test": None},
        ]
        _compute_mdo_for_baseline(rows, {"synthetic__t": self._task()})
        for r in rows:
            assert r["mdo_available"] is None
            assert r["mdo_not_available_reason"] == "no_task_or_test"


class TestNonTerminatingMutantsExcluded:
    """非终止变异体必须**双向**排除出 MTR/MDR 分母（2026-10-11 修正）。

    场景（实测来源）：QuixBugs `bitcount` 在 Python 负数上永不终止
    （`while n: n &= n-1`，负数是无限二进制补码）→ 其 `cond_negate` 变异体
    让函数在所有输入上挂死 → 行为探针无法终止。

    两种错误处理方式都会污染指标：
    ① 折叠为 `divergent=False` → 被误算为"等价变异体"；
    ② 记入分母 → 被算成"测试未判别"（把变异体的缺陷记到测试头上）。

    实测后果（修正前）：强断言测试的 MDR（0.5）**低于**弱断言测试（0.75），
    因为非终止变异体始终落在分母里，而它与断言质量无关。
    """

    def test_hanging_mutant_is_flagged_not_counted(self) -> None:
        """让函数挂死的变异体应标 non_terminating，且不进入分母。"""
        from experiments.mutation_testing import MutationGenerator
        from src.measurement.mdo import compute_mdo

        # 与 bitcount 同构：负数输入下 `n & (n-1)` 在 Python 上永不终止
        gold = "def bc(n):\n    c = 0\n    while n:\n        n &= n - 1\n        c += 1\n    return c\n"
        pool = MutationGenerator().generate(gold)
        # 只保留"条件取反"类（会破坏 while 条件 → 挂死）
        hanging = [m for m in pool if m.mutant_type == "boolean_negation"] or pool[:1]
        suite = "from t import bc\n\ndef test_bc():\n    assert bc(5) == 2\n"
        r = compute_mdo(base_code=gold, test_code=suite, module_name="t", mutants=hanging, timeout_seconds=10)
        assert r.available is True
        d = r.as_dict()
        # 分母口径必须显式透出，且 可评估 + 非终止 == 池规模
        assert d["mdo_evaluable"] + d["mdo_non_terminating"] == d["mdo_pool_size"]
        # 若全部变异体都挂死，则 MTR/MDR 均为 None（不可测），而非 0
        if d["mdo_evaluable"] == 0:
            assert d["mtr"] is None and d["mdr"] is None

    def test_as_dict_exposes_denominator_breakdown(self) -> None:
        from src.measurement.mdo import compute_mdo

        base = "def f(x):\n    return x + 1\n"
        suite = "from t import f\n\ndef test_f():\n    assert f(1) == 2\n"
        r = compute_mdo(
            base_code=base,
            test_code=suite,
            module_name="t",
            mutants=[_M("def f(x):\n    return x + 2\n")],
        )
        d = r.as_dict()
        assert "mdo_evaluable" in d and "mdo_non_terminating" in d
        assert d["mdo_evaluable"] >= 1
