"""规格欠定度（SAI）框架回归守卫。

核心不变量：

1. **SAI 度量"实现之间的分歧"**，**gold 偏离率**度量"规格已确定但参考实现另选一支"——
   两者必须**可分离**（实测 `get_factors`：SAI=0.0 而 gold 偏离率=1.0）。
2. **gold 不参与"确定/欠定"判定**（只用于对比），否则会把"参考的任意选择"
   误当成分歧。
3. **共识不得用于判断期望值正误**（附录 L/M 的否定结果），因此本模块**只测量、不修改**。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.spec_ambiguity import (
    ProbePoint,
    build_probe_inputs,
    compute_sai,
    render_report,
)

# 参考实现：返回"全部因子"（与下面的错误/不同实现形成可控差异）
_GOLD = "def f(n):\n    return sorted([d for d in range(1, n + 1) if n % d == 0])\n"
# 三份**互相一致**但与 gold 不同的实现（模拟实测的 get_factors 现象）
_IMPL_A = "def f(n):\n    out = []\n    for d in range(1, n + 1):\n        if n % d == 0:\n            out.append(d)\n    return out\n"
_IMPL_B = "def f(n):\n    return [d for d in range(1, n + 1) if not n % d]\n"
_IMPL_C = "def f(n):\n    import math\n    return [d for d in range(1, n + 1) if n % d == 0]\n"
# 一个"与多数不一致"的实现（制造真正的欠定点）
_IMPL_DIVERGENT = "def f(n):\n    return [2] if n % 2 == 0 else [n]\n"


class TestProbePointSemantics:
    def test_ambiguous_when_implementations_disagree(self) -> None:
        p = ProbePoint(args=[12], behaviors=["ok:[1]", "ok:[2]"], gold_behavior="ok:[1]")
        assert p.is_ambiguous is True
        assert p.distinct == 2

    def test_determined_and_gold_deviation(self) -> None:
        """全体一致但与 gold 不同 → 不算歧义，算 gold 偏离。"""
        p = ProbePoint(args=[12], behaviors=["ok:[1,2]", "ok:[1,2]"], gold_behavior="ok:[2]")
        assert p.is_ambiguous is False
        assert p.gold_deviates is True

    def test_determined_and_gold_agrees(self) -> None:
        p = ProbePoint(args=[12], behaviors=["ok:[1,2]", "ok:[1,2]"], gold_behavior="ok:[1,2]")
        assert p.is_ambiguous is False
        assert p.gold_deviates is False

    def test_ambiguous_excludes_gold_deviation(self) -> None:
        """欠定点不计入 gold 偏离（偏离只在确定点上有定义）。"""
        p = ProbePoint(args=[1], behaviors=["ok:a", "ok:b"], gold_behavior="ok:a")
        assert p.is_ambiguous is True
        assert p.gold_deviates is False


class TestSAISeparation:
    def test_sai_zero_but_full_gold_deviation(self) -> None:
        """实测复现：实现全一致（SAI=0）但 gold 全偏离（偏离率=1.0）。"""
        probes = [[1], [2], [6], [12], [7]]
        # gold 在所有探针上返回固定值 [99]，与三份实现（返回值随 n 变化）必然不同
        gold = "def f(n):\n    return [99]\n"
        r = compute_sai(
            implementations=[_IMPL_A, _IMPL_B, _IMPL_C],
            gold_code=gold,
            fn_name="f",
            probes=probes,
            timeout=15,
        )
        assert r.available is True
        assert r.sai == 0.0, "三份实现互相一致 → SAI 必须为 0"
        assert r.gold_deviation_rate == 1.0, "gold 与全体不同 → 偏离率必须为 1"

    def test_sai_positive_when_implementations_diverge(self) -> None:
        probes = [[1], [2], [6]]
        r = compute_sai(
            implementations=[_IMPL_A, _IMPL_C, _IMPL_DIVERGENT],
            gold_code=_IMPL_A,
            fn_name="f",
            probes=probes,
            timeout=15,
        )
        assert r.available is True
        assert r.n_ambiguous >= 1, "含分歧实现时必须有欠定点"
        assert r.sai is not None and r.sai > 0

    def test_gold_not_used_for_ambiguity_decision(self) -> None:
        """gold 换成任意值都不得改变 SAI（只影响偏离率）。"""
        probes = [[6], [12]]
        r1 = compute_sai(implementations=[_IMPL_A, _IMPL_B], gold_code=_IMPL_A, fn_name="f", probes=probes, timeout=15)
        r2 = compute_sai(
            implementations=[_IMPL_A, _IMPL_B], gold_code=_IMPL_DIVERGENT, fn_name="f", probes=probes, timeout=15
        )
        assert r1.sai == r2.sai, "SAI 必须与 gold 无关"
        assert r1.gold_deviation_rate != r2.gold_deviation_rate


class TestFailClosed:
    def test_needs_two_implementations(self) -> None:
        r = compute_sai(implementations=[_IMPL_A], gold_code=_GOLD, fn_name="f", probes=[[1]], timeout=10)
        assert r.available is False
        assert r.not_available_reason == "need_at_least_2_implementations"

    def test_no_probes(self) -> None:
        r = compute_sai(implementations=[_IMPL_A, _IMPL_B], gold_code=_GOLD, fn_name="f", probes=[], timeout=10)
        assert r.available is False
        assert r.not_available_reason == "no_probes"

    def test_probe_builder_returns_empty_for_unknown_fn(self) -> None:
        assert build_probe_inputs("nope", _GOLD, limit=5) == []


class TestReport:
    def test_report_contains_both_metrics(self) -> None:
        r = compute_sai(
            implementations=[_IMPL_A, _IMPL_B, _IMPL_C],
            gold_code="def f(n):\n    return [n]\n",
            fn_name="f",
            probes=[[6], [12]],
            timeout=15,
        )
        txt = render_report([r])
        assert "SAI" in txt
        assert "gold 偏离率" in txt
        assert "`f`" in txt

    def test_report_handles_unavailable(self) -> None:
        r = compute_sai(implementations=[], gold_code=_GOLD, fn_name="f", probes=[[1]], timeout=5)
        txt = render_report([r])
        assert "`f`" in txt
