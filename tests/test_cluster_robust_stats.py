"""S13/S11/T6 回归守卫（2026-10-11 独立评审落地）。

三块内容，对应外部评审的三个实测缺陷：

- **S13/F2（聚类稳健统计）**：项目把 87 个任务标签当独立样本做配对检验，
  但实测这些标签只对应 **26 个唯一程序体**（`BUG_PATTERNS` 仅 16 个模板，
  逐任务"噪声"只是行尾注释）——精确度被高估约 3.35 倍。本文件把 26 这个
  实测事实**锁死**，并锁定簇级配对检验（先簇内取均值、再在簇级做 t +
  符号检验 + 效应量）的手算值与退化行为。
- **S11/F9（token 记账健全性）**：7 份批次中 `plain_llm` / `plain_llm_df`
  的 `token_usage` 整臂全为 0（含 `llm_calls`）而 `generated_test` 非空——
  成本结论不可计算却仍被输出。本文件锁定"≥50% 行无记账 → 成本列
  `NOT_COMPUTABLE`，不输出数字"。
- **T6（MDO 饱和标记）**：`compute_mdo` 在池仅 2（下限 29）时仍输出
  `mtr=1.0` / `mdr=1.0`，下游误读为"判别力满分"。修正采用**序列化边界
  拦截**：属性层保留计算值（计算正确性仍可测），`as_dict()` 出口把规范键
  `mtr`/`mdr`/`crash_rate` 置 `None` 并给出 `mdo_provisional` / `mdo_raw`
  披露，`status` 新增第三态 `provisional_pool`。

纪律：零 LLM 调用；`build_cluster_map` 只读导入 `src/datasets/synthetic_dataset.py`
（该文件不修改）；数据全部为手工构造或本地合成数据集重建。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.statistical_analysis import (
    _NOT_COMPUTABLE_CELL,
    _TOKEN_ACCOUNTING_ZERO_SHARE_THRESHOLD,
    _cost_report_lines,
    build_cluster_map,
    cluster_map_summary,
    cluster_robust_paired_test,
    cost_analysis,
    cost_per_solved,
    program_fingerprint,
    run_all_statistics,
    strip_line_comments,
    token_accounting_sanity,
)

# 独立评审实测事实（锁定，不得"顺手放宽"）：87 个任务标签 → 26 个唯一程序体
_EXPECTED_CLUSTERS_87_42 = 26
_EXPECTED_SIZE_DISTRIBUTION_87_42 = {1: 5, 2: 7, 3: 4, 4: 5, 5: 1, 6: 1, 7: 1, 9: 2}

_PRICES: dict[str, Any] = {
    "models": {
        "m1": {
            "input_per_mtok": 1.0,
            "output_per_mtok": 2.0,
            "currency": "USD",
            "source": "test",
            "as_of": "2026-10-11",
        }
    }
}


def _synthetic_task_ids(task_count: int = 87) -> list[str]:
    return [f"synthetic__task_{i:04d}" for i in range(task_count)]


def _key_fn(mapping: dict[str, str]):
    """把静态簇映射包成 cluster_key_fn（缺键 → 单例簇，与生产口径一致）。"""

    def _key(task_id: str) -> str:
        return mapping.get(task_id, f"unmapped::{task_id}")

    return _key


# ─────────────── S13：簇映射（实测事实锁定 + 可复现构造） ───────────────


class TestClusterMap:
    """`build_cluster_map`：簇构造必须可从工件（task_count, seed）复现。"""

    def test_87_tasks_seed42_yield_26_clusters(self) -> None:
        """**实测事实锁定**：87 个任务标签只对应 26 个唯一程序体。

        这是独立评审实测确认的数字（`BUG_PATTERNS` 仅 16 个模板，噪声只是
        行尾注释）——聚类稳健统计的全部意义建立在此事实之上，故必须锁死。
        """
        cluster_map = build_cluster_map(_synthetic_task_ids(87), task_count=87, seed=42)
        assert len(cluster_map) == 87
        assert cluster_map_summary(cluster_map)["n_clusters"] == _EXPECTED_CLUSTERS_87_42

    def test_cluster_size_distribution_locked(self) -> None:
        """簇规模分布锁定（1×5 / 2×7 / 3×4 / 4×5 / 5×1 / 6×1 / 7×1 / 9×2）。"""
        summary = cluster_map_summary(build_cluster_map(_synthetic_task_ids(87), task_count=87, seed=42))
        assert summary["size_distribution"] == _EXPECTED_SIZE_DISTRIBUTION_87_42
        assert sum(k * v for k, v in summary["size_distribution"].items()) == 87
        assert summary["n_unmapped"] == 0

    def test_is_deterministic_and_order_independent(self) -> None:
        """同参两次调用结果一致；任务 ID 顺序不影响簇结构。"""
        ids = _synthetic_task_ids(87)
        first = build_cluster_map(ids, task_count=87, seed=42)
        second = build_cluster_map(ids, task_count=87, seed=42)
        assert first == second
        shuffled = list(reversed(ids))
        assert cluster_map_summary(build_cluster_map(shuffled, task_count=87, seed=42))["n_clusters"] == 26

    def test_seed_prefix_merged_for_pooled_seeds(self) -> None:
        """多种子拼接口径（`--pool-seeds`）：`s<seed>__` 前缀先剥离再查表。

        261 = 3 种子 × 87 任务 → 仍为 **26** 簇（同一程序体跨种子必须合并，
        这正是任务级 n 虚高的来源）。
        """
        ids = [f"s{seed}__{tid}" for seed in (0, 1, 2) for tid in _synthetic_task_ids(87)]
        summary = cluster_map_summary(build_cluster_map(ids, task_count=87, seed=42))
        assert summary["n_tasks"] == 261
        assert summary["n_clusters"] == 26
        assert summary["n_unmapped"] == 0

    def test_unmapped_task_degrades_to_singleton(self) -> None:
        """查不到的任务（真实基准 / 前缀异常）各成单例簇，不丢弃也不并簇。"""
        ids = [*_synthetic_task_ids(3), "quixbugs__bitcount", "whatever"]
        summary = cluster_map_summary(build_cluster_map(ids, task_count=87, seed=42))
        assert summary["n_unmapped"] == 2
        assert summary["n_clusters"] == summary["n_tasks"] - len(_synthetic_task_ids(3)) + 3

    def test_empty_input_no_exception(self) -> None:
        """空输入保守降级：不抛异常、返回空映射与全 0 摘要。"""
        summary = cluster_map_summary(build_cluster_map([], task_count=87, seed=42))
        assert summary == {"n_tasks": 0, "n_clusters": 0, "n_unmapped": 0, "size_distribution": {}}

    def test_program_fingerprint_ignores_line_comments(self) -> None:
        """簇 ID 的构造依据**只是**行尾注释差异：去注释后逐字节相同 → 同指纹。

        同时锁定 sha256 口径（64 位 hex）与 `strip_line_comments` 的语义。
        """
        base = "def solve(xs):\n    return sum(xs)\n"
        noisy = "def solve(xs):\n    return sum(xs)  # noise_seed=7\n"
        assert strip_line_comments(noisy) == strip_line_comments(base)
        assert program_fingerprint(noisy) == program_fingerprint(base)
        assert len(program_fingerprint(base)) == 64
        # 程序体不同 → 指纹不同（聚类不能把不同实现合并）
        other = "def solve(xs):\n    return sum(xs) + 1\n"
        assert program_fingerprint(other) != program_fingerprint(base)


# ─────────────── S13：簇级配对检验（手算值 + 退化行为） ───────────────


class TestClusterRobustPairedTest:
    """先簇内取均值、再在簇级做配对检验（每个程序体只投一票）。"""

    @staticmethod
    def _four_cluster_case() -> dict[str, Any]:
        """4 个簇、簇级差值 [1, 1, 1, −1]：delta=0.5、sd=1.0、se=0.5、df=3。"""
        mapping = {"t1": "c1", "t2": "c2", "t3": "c3", "t4": "c4"}
        pairs = [("t1", 1.0, 0.0), ("t2", 1.0, 0.0), ("t3", 1.0, 0.0), ("t4", 0.0, 1.0)]
        return cluster_robust_paired_test(pairs, _key_fn(mapping))

    def test_hand_computed_delta_ci_and_t(self) -> None:
        """手算值锁定（scipy.stats.t.ppf(0.975, 3) = 3.1824463052837078）。"""
        res = self._four_cluster_case()
        assert res["n_pairs"] == 4
        assert res["n_clusters"] == 4
        assert res["delta"] == pytest.approx(0.5)
        assert res["df"] == 3
        assert res["t"] == pytest.approx(1.0)
        assert res["p_value"] == pytest.approx(0.3910022189557705)
        assert res["ci_low"] == pytest.approx(0.5 - 3.1824463052837078 * 0.5)
        assert res["ci_high"] == pytest.approx(0.5 + 3.1824463052837078 * 0.5)
        assert res["status"] == "ok"

    def test_bootstrap_ci_is_reproducible_and_brackets_delta(self) -> None:
        """bootstrap CI 固定 seed（42）逐位可复现，且包住点估计。"""
        first = self._four_cluster_case()
        second = self._four_cluster_case()
        assert (first["boot_ci_low"], first["boot_ci_high"]) == (second["boot_ci_low"], second["boot_ci_high"])
        assert first["bootstrap_seed"] == 42
        assert first["boot_ci_low"] <= first["delta"] <= first["boot_ci_high"]

    def test_cluster_mean_is_taken_before_testing(self) -> None:
        """簇内先取均值：同一簇内 3 个任务（2 胜 1 负）压成 1 个观测。

        若误按任务级计算，delta 会等于 (2−1)/3；正确口径为簇级均值差
        (2/3 − 1/3) = 1/3 且 n_clusters=1。
        """
        mapping = {"a": "c1", "b": "c1", "c": "c1"}
        pairs = [("a", 1.0, 0.0), ("b", 1.0, 0.0), ("c", 0.0, 1.0)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["n_pairs"] == 3
        assert res["n_clusters"] == 1
        assert res["delta"] == pytest.approx(1.0 / 3.0)
        assert res["status"] == "single_cluster"

    def test_all_same_sign_sign_test_p_small(self) -> None:
        """全部同号（6 簇全胜）→ 精确符号检验 p = 2/2⁶ = 0.03125（小）。"""
        mapping = {f"t{i}": f"c{i}" for i in range(6)}
        pairs = [(f"t{i}", 1.0, 0.0) for i in range(6)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["sign_wins"] == 6
        assert res["sign_losses"] == 0
        assert res["sign_p"] == pytest.approx(0.03125)
        assert res["sign_p"] < 0.05

    def test_all_ties_sign_test_p_equals_one(self) -> None:
        """全部持平（簇级差值恒 0）→ 符号检验 p=1，t/p 为 nan，CI 退化为点。"""
        mapping = {f"t{i}": f"c{i}" for i in range(5)}
        pairs = [(f"t{i}", 1.0, 1.0) for i in range(5)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["delta"] == 0.0
        assert res["sign_p"] == 1.0
        assert res["sign_ties"] == 5
        assert math.isnan(res["t"]) and math.isnan(res["p_value"])
        assert (res["ci_low"], res["ci_high"]) == (0.0, 0.0)

    def test_constant_nonzero_diff_gives_infinite_t(self) -> None:
        """簇级差值恒定非零（退化配对）→ t=+inf / p=0（与历史 t 检验同口径）。"""
        mapping = {f"t{i}": f"c{i}" for i in range(4)}
        pairs = [(f"t{i}", 1.0, 0.0) for i in range(4)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["t"] == float("inf")
        assert res["p_value"] == 0.0
        assert (res["ci_low"], res["ci_high"]) == (1.0, 1.0)

    @pytest.mark.parametrize(
        ("all_win", "expected_cliffs", "expected_a12", "expected_effect"),
        [
            (True, 1.0, 1.0, "large"),
            (False, -1.0, 0.0, "large"),
        ],
    )
    def test_effect_size_boundaries(
        self, all_win: bool, expected_cliffs: float, expected_a12: float, expected_effect: str
    ) -> None:
        """效应量边界：全胜 δ=+1 / A12=1；全负 δ=−1 / A12=0；均为 large。"""
        mapping = {f"t{i}": f"c{i}" for i in range(4)}
        pairs = [(f"t{i}", 1.0, 0.0) if all_win else (f"t{i}", 0.0, 1.0) for i in range(4)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["cliffs_delta"] == pytest.approx(expected_cliffs)
        assert res["a12"] == pytest.approx(expected_a12)
        assert res["cliffs_effect"] == expected_effect

    def test_effect_size_all_ties_is_negligible(self) -> None:
        """全平效应量：Cliff's δ=0（negligible）、A12=0.5（随机水平）。"""
        mapping = {f"t{i}": f"c{i}" for i in range(3)}
        pairs = [(f"t{i}", 0.0, 0.0) for i in range(3)]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["cliffs_delta"] == 0.0
        assert res["cliffs_effect"] == "negligible"
        assert res["a12"] == pytest.approx(0.5)

    def test_report_carries_effect_size_not_only_p(self) -> None:
        """报告口径必须有效应量（评审要求：不能只有 p 值）。"""
        res = self._four_cluster_case()
        for key in ("delta", "ci_low", "ci_high", "t", "df", "sign_p", "concordance", "cliffs_delta", "a12"):
            assert key in res
        assert res["cliffs_delta"] is not None and res["a12"] is not None

    def test_concordance_is_size_weighted_within_cluster_agreement(self) -> None:
        """簇内一致率：c1（3 个任务同向）贡献 3/3，c2（1 胜 1 负）贡献 1/2。

        加权 (3 + 1) / 5 = 0.8；单任务簇不计入（无"一致"可言）。
        """
        mapping = {"a": "c1", "b": "c1", "c": "c1", "d": "c2", "e": "c2", "f": "c3"}
        pairs = [
            ("a", 1.0, 0.0),
            ("b", 1.0, 0.0),
            ("c", 1.0, 0.0),
            ("d", 1.0, 0.0),
            ("e", 0.0, 1.0),
            ("f", 1.0, 0.0),
        ]
        res = cluster_robust_paired_test(pairs, _key_fn(mapping))
        assert res["concordance"] == pytest.approx(0.8)
        assert res["cluster_size_distribution"] == {1: 1, 2: 1, 3: 1}

    def test_none_values_are_skipped(self) -> None:
        """None 值的对跳过（不可测 → 不并入分母，与 M1 口径一致）。"""
        mapping = {"a": "c1", "b": "c2"}
        res = cluster_robust_paired_test([("a", None, 0.0), ("b", 1.0, 0.0)], _key_fn(mapping))
        assert res["n_pairs"] == 1
        assert res["n_clusters"] == 1
        assert res["status"] == "single_cluster"

    def test_empty_input_degrades_without_exception(self) -> None:
        """空输入保守降级：不抛异常，n_clusters=0 且统计量全 nan。"""
        res = cluster_robust_paired_test([], lambda tid: f"c::{tid}")
        assert res["n_pairs"] == 0
        assert res["n_clusters"] == 0
        assert res["status"] == "insufficient_data"
        assert res["sign_p"] == 1.0
        assert all(math.isnan(res[k]) for k in ("delta", "ci_low", "ci_high", "t", "df", "concordance"))


# ─────────────── S11：token 记账健全性（成本列 NOT_COMPUTABLE） ───────────────


def _token_row(task_id: str, input_tokens: int, *, generated_test: str | None = None) -> dict:
    """构造结果行：token_usage 三字段一致（by_model 同值），可选 generated_test。"""
    row: dict[str, Any] = {
        "task_id": task_id,
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": 0,
            "total_tokens": input_tokens,
            "by_model": {"m1": input_tokens},
        },
    }
    if generated_test is not None:
        row["generated_test"] = generated_test
    return row


class TestTokenAccountingSanity:
    """S11：≥50% 行 token_usage 为 0/缺失 → 成本结论 NOT_COMPUTABLE。"""

    def test_threshold_contract_locked(self) -> None:
        """阈值锁定 50%（评审口径），且边界取"≥"。"""
        assert _TOKEN_ACCOUNTING_ZERO_SHARE_THRESHOLD == 0.5
        # 2 行中 1 行无记账 = 50% → 触发
        half = [_token_row("t1", 1000), _token_row("t2", 0)]
        assert token_accounting_sanity(half)["computable"] is False
        assert token_accounting_sanity(half)["zero_share"] == pytest.approx(0.5)
        # 3 行中 1 行无记账 = 33.3% → 不触发
        third = [_token_row("t1", 1000), _token_row("t2", 1000), _token_row("t3", 0)]
        assert token_accounting_sanity(third)["computable"] is True

    def test_zero_token_arm_is_not_computable(self) -> None:
        """整臂 0 记账（实测形态：generated_test 非空而 token 全 0）→ 判不可计算。"""
        rows = [
            _token_row("t1", 0, generated_test="def test_a():\n    assert True\n"),
            _token_row("t2", 0, generated_test="def test_b():\n    assert True\n"),
            _token_row("t3", 1000, generated_test="def test_c():\n    assert True\n"),
        ]
        sanity = token_accounting_sanity(rows)
        assert sanity["computable"] is False
        assert sanity["n_without_accounting"] == 2
        assert sanity["zero_share"] == pytest.approx(2 / 3)
        assert "token_usage 为 0 或缺失" in sanity["reason"]

    def test_missing_token_usage_key_counts_as_unaccounted(self) -> None:
        """token_usage 整键缺失（旧行/失败行）同样计入"无记账"。"""
        sanity = token_accounting_sanity([{"task_id": "t1", "passed": True}, _token_row("t2", 5)])
        assert sanity["n_without_accounting"] == 1
        assert sanity["computable"] is False

    def test_empty_arm_is_computable_no_false_alarm(self) -> None:
        """空臂（无结果行）→ 不误报记账断裂，历史 "—" 降级口径保留。"""
        assert token_accounting_sanity([])["computable"] is True

    def test_cost_report_renders_not_computable_without_numbers(self) -> None:
        """成本表：记账断裂的臂 → 成本/任务与成本/检出均为 NOT_COMPUTABLE。

        这是本项的核心断言：**不得输出数字**（"0.0000" 会被读成"免费"，
        "—" 会被读成"未计价"，两者都掩盖根因"记账缺失"）。同表另一臂
        （aitester）记账正常 → 正常输出数字，证明拦截是按臂生效而非整表关闭。
        """
        broken = [
            _token_row("t1", 0, generated_test="def test_a():\n    assert True\n"),
            _token_row("t2", 0, generated_test="def test_b():\n    assert True\n"),
        ]
        cost_rows = cost_analysis({"aitester": [_token_row("g1", 1_000_000)], "plain_llm": broken}, _PRICES)
        by_baseline = {r["baseline"]: r for r in cost_rows}
        assert by_baseline["plain_llm"]["token_accounting_ok"] is False
        assert by_baseline["aitester"]["token_accounting_ok"] is True

        text = "\n".join(_cost_report_lines(cost_rows, _PRICES, det_rates={"aitester": 50.0, "plain_llm": 10.0}))
        assert f"| plain_llm | 2 | 0 | 0 | {_NOT_COMPUTABLE_CELL} | {_NOT_COMPUTABLE_CELL} | — |" in text
        # 记账正常的臂照常给数字（防止"一刀切关掉成本节"的伪修复）
        assert "| aitester | 1 | 1000000 | 0 | 1.0000 | 2.0000 | USD |" in text
        assert "0.0000" not in text  # 断裂臂不得出现任何成本数字
        assert "NOT_COMPUTABLE（S11 token 记账健全性" in text
        assert "2/2 行（100.0%）" in text

    def test_not_computable_disclosed_even_without_priced_arm(self) -> None:
        """全部臂都未计价（无表格）时，记账断裂仍须显式披露（不得静默）。"""
        cost_rows = cost_analysis({"plain_llm": [_token_row("t1", 0)]}, _PRICES)
        text = "\n".join(_cost_report_lines(cost_rows, _PRICES))
        assert "价目未登记" in text
        assert "NOT_COMPUTABLE（S11 token 记账健全性" in text
        assert "`plain_llm`" in text

    def test_not_computable_arm_shows_no_currency(self) -> None:
        """记账断裂的臂即便价目已登记，也不得残留币种（"USD + NOT_COMPUTABLE"会误导）。"""
        rows = [_token_row("t1", 1_000_000), _token_row("t2", 0)]  # 50% → 判断裂
        cost_rows = cost_analysis({"plain_llm": rows}, _PRICES)
        assert cost_rows[0]["currency"] == "USD"  # 价目已登记（行级汇总仍成立）
        text = "\n".join(_cost_report_lines(cost_rows, _PRICES, det_rates={"plain_llm": 10.0}))
        assert f"| plain_llm | 2 | 1000000 | 0 | {_NOT_COMPUTABLE_CELL} | {_NOT_COMPUTABLE_CELL} | — |" in text

    def test_cost_rows_flag_is_carried(self) -> None:
        """记账健全性判定随成本行携带（下游可消费，不必重算）。"""
        good = cost_analysis({"aitester": [_token_row("t1", 1000)]}, _PRICES)[0]
        bad = cost_analysis({"plain_llm": [_token_row("t1", 0)]}, _PRICES)[0]
        assert good["token_accounting_ok"] is True
        assert good["token_accounting_reason"] == ""
        assert bad["token_accounting_ok"] is False
        assert bad["token_zero_rows"] == 1

    def test_cost_per_solved_degrades_when_accounting_broken(self) -> None:
        """$/solved 与 $/task 同源：记账断裂 → None（不输出派生数字）。"""
        rows = [_token_row("t1", 0, generated_test="def test_a():\n    assert True\n")]
        rows[0]["patch_correct"] = 1
        cost_rows = cost_analysis({"plain_llm": rows}, _PRICES)
        assert cost_per_solved(cost_rows, {"plain_llm": rows})["plain_llm"] is None

    def test_hand_written_cost_rows_keep_legacy_format(self) -> None:
        """手写 cost_rows（不含新键）→ 历史表格格式逐位不变（向后兼容锁）。"""
        rows = [
            {
                "baseline": "a",
                "n_tasks": 1,
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "by_model": {"m1": 2_000_000},
                "missing_models": [],
                "unattributed_tokens": 0,
                "cost": 3.0,
                "cost_per_task": 3.0,
                "currency": "USD",
                "priced": True,
            }
        ]
        text = "\n".join(_cost_report_lines(rows, _PRICES, det_rates={"a": 50.0}))
        assert "| a | 1 | 1000000 | 1000000 | 3.0000 | 6.0000 | USD |" in text
        assert "NOT_COMPUTABLE" not in text


# ─────────────── T6：MDO 池不足时的序列化边界拦截 ───────────────

_MDO_BASE = "def f(x):\n    if x > 0:\n        return x + 1\n    return 0\n"
_MDO_STRONG = "from t import f\n\ndef test_f():\n    assert f(1) == 2\n    assert f(-5) == 0\n    assert f(0) == 0\n"


class _M:
    """最小变异体替身（与 tests/test_mdo_metrics.py 同构）。"""

    def __init__(self, code: str, mutant_type: str = "probe") -> None:
        self.code = code
        self.mutant_type = mutant_type
        self.description = mutant_type
        self.line_no = 1


class TestMDOProvisionalPool:
    """T6：池未达下限（实测池 2 < 下限 29）时，规范出口不得给数字。"""

    _MUTANTS: ClassVar[list[_M]] = [
        _M("def f(x):\n    if x > 0:\n        return x + 2\n    return 0\n", "numeric_offset"),
        _M("def f(x):\n    if x > 0:\n        return x + 1\n    return None\n", "return_void"),
    ]

    def test_provisional_pool_blocks_serialized_numbers(self) -> None:
        """真实计算路径：池=2（<29）→ status=provisional_pool，出口 mtr/mdr=None。

        同时锁定**属性层仍是计算值**（计算正确性不受影响——判别逻辑由
        tests/test_mdo_metrics.py 的弱/强断言用例覆盖）。
        """
        from src.measurement.mdo import compute_mdo, pool_floor

        res = compute_mdo(base_code=_MDO_BASE, test_code=_MDO_STRONG, module_name="t", mutants=self._MUTANTS)
        assert res.available is True
        assert res.pool_size == 2 < pool_floor(0.10)
        assert res.pool_floor_ok is False
        assert res.status == "provisional_pool"
        # 属性层（计算路径）：弱断言/强断言判别逻辑仍可测
        assert res.mutant_trigger_rate == 1.0
        assert res.mutant_discrimination_rate == 1.0
        # 出口层（序列化边界）：下游拿不到可误读的数字
        payload = res.as_dict()
        assert payload["mtr"] is None
        assert payload["mdr"] is None
        assert payload["crash_rate"] is None
        assert payload["mdo_provisional"] is True
        assert payload["mdo_status"] == "provisional_pool"
        assert payload["mdo_pool_floor_ok"] is False

    def test_serialized_payload_is_json_serializable_plain_dict(self) -> None:
        """`mdo_raw` 必须是**普通 dict**（JSON 可序列化），供 run_benchmark 写工件。"""
        from src.measurement.mdo import MDOResult

        res = MDOResult(available=True, pool_size=2, pool_floor_ok=False, status="provisional_pool")
        payload = res.as_dict()
        assert isinstance(payload["mdo_raw"], dict)
        assert set(payload["mdo_raw"]) == {"mtr", "mdr", "crash_rate"}
        assert json.dumps(payload)  # 不得抛异常（结果行要落 JSON 工件）
        assert json.loads(json.dumps(payload))["mdo_provisional"] is True

    def test_raw_values_kept_for_audit(self) -> None:
        """原始值仍可审计（`mdo_raw`），但不占会被按数字读取的规范键。"""
        from src.measurement.mdo import MDOResult

        res = MDOResult(
            available=True,
            pool_size=2,
            pool_floor_ok=False,
            mutant_trigger_rate=1.0,
            mutant_discrimination_rate=1.0,
            crash_rate=0.0,
            status="provisional_pool",
        )
        payload = res.as_dict()
        assert payload["mdo_raw"] == {"mtr": 1.0, "mdr": 1.0, "crash_rate": 0.0}

    def test_measured_pool_keys_unchanged(self) -> None:
        """池达下限（pool_floor_ok=True）→ status=measured，键集合保持历史口径。"""
        from src.measurement.mdo import MDOResult

        res = MDOResult(available=True, pool_size=40, pool_floor_ok=True, mutant_trigger_rate=0.5, status="measured")
        payload = res.as_dict()
        assert payload["mdo_status"] == "measured"
        assert payload["mtr"] == 0.5
        assert "mdo_provisional" not in payload
        assert "mdo_raw" not in payload

    def test_not_measurable_keys_unchanged(self) -> None:
        """不可测（available=False）→ 历史键集合与 reason 语义不变。"""
        from src.measurement.mdo import MDOResult

        payload = MDOResult(not_available_reason="empty_mutant_pool").as_dict()
        assert payload["mdo_available"] is False
        assert payload["mdo_not_available_reason"] == "empty_mutant_pool"
        assert payload["mtr"] is None and payload["mdr"] is None
        assert "mdo_provisional" not in payload


# ─────────────── S13：报告节（默认关闭 → 历史数字逐位不变） ───────────────


def _write_batch(root: Path, name: str, arms: dict[str, list[dict]]) -> None:
    """写 benchmark_*.json 批次（行含 detection_rate，满足 X2 的 M1 schema 门禁）。"""
    payload = {"dataset": "synthetic", "results": {arm: {"details": rows} for arm, rows in arms.items()}}
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _arm_rows(threshold: int, *, offset: int = 0) -> list[dict]:
    """87 行：i % threshold == 0 → detection 1（簇内不一致的真实形态）。"""
    return [
        {
            "task_id": f"synthetic__task_{i:04d}",
            "passed": (i + offset) % threshold == 0,
            "detection_rate": 1.0 if i % threshold == 0 else 0.0,
        }
        for i in range(87)
    ]


def _paired_test_table(report_text: str) -> list[str]:
    """抽出"## 配对t检验结果"表体（历史可比性断言用）。"""
    lines = report_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 配对t检验结果"))
    return [line for line in lines[start:] if line.startswith("|")][:4]


class TestClusterRobustReportSection:
    """报告层：新增 `cluster_robust` 节，且默认关闭时输出逐位不变。"""

    @staticmethod
    def _make_fixture(tmp_path: Path) -> None:
        _write_batch(
            tmp_path,
            "benchmark_synthetic_20261011_120000.json",
            {
                "aitester": _arm_rows(3),
                "plain_llm": _arm_rows(2, offset=1),
                "plain_llm_df": _arm_rows(5, offset=2),
            },
        )

    def test_default_off_has_no_cluster_section(self, tmp_path: Path) -> None:
        """默认（不带 --cluster-robust）→ 报告不含聚类节（历史口径不变）。"""
        self._make_fixture(tmp_path)
        report = tmp_path / "off.md"
        run_all_statistics(str(tmp_path), str(report), price_table={"models": {}})
        text = report.read_text(encoding="utf-8")
        assert "## 聚类稳健统计（cluster_robust" not in text
        assert "--cluster-robust" not in text

    def test_enabled_appends_section_without_changing_history(self, tmp_path: Path) -> None:
        """开启 → 追加 cluster_robust 节；历史非聚类数字（t 检验表）逐位不变。"""
        self._make_fixture(tmp_path)
        off = tmp_path / "off.md"
        on = tmp_path / "on.md"
        run_all_statistics(str(tmp_path), str(off), price_table={"models": {}})
        run_all_statistics(
            str(tmp_path),
            str(on),
            price_table={"models": {}},
            cluster_robust=True,
            cluster_task_count=87,
            cluster_seed=42,
        )
        off_text = off.read_text(encoding="utf-8")
        on_text = on.read_text(encoding="utf-8")

        assert "## 聚类稳健统计（cluster_robust" in on_text
        assert "**26 个唯一程序体**" in on_text
        assert "任务级 n=87 → 簇级 n=26" in on_text or "| 87 | 26 |" in on_text
        # 历史可比性：配对 t 检验表逐位一致
        assert _paired_test_table(on_text) == _paired_test_table(off_text)
        # 复算命令带同参（簇级数字可复现）
        assert "--cluster-robust --cluster-task-count 87 --cluster-seed 42" in on_text
