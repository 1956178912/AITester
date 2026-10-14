# SpecExpr 确认性实验分析脚本的回归测试（2026-10-14）
#
# 覆盖 experiments/emse_specexpr_confirm.py 的关键纪律：
#   - 种子内配对、池化计数（**跨种子 task_id 错配防护**——两种子 task_id
#     相同但任务内容不同，错配会产生虚假配对）；
#   - 统计量与项目定案值对齐（pilot b=7/c=1/n=50 → δ=12pp、p=0.0703）；
#   - 预注册判定规则边界；
#   - 不对称应用审计、回退子集敏感性、机制统计的 None 处理；
#   - provenance 校验与工件缺失的可读诊断。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.emse_specexpr_confirm import (
    CONFIRM_DELTA_PP,
    CONFIRM_P,
    TREND_P,
    MissingArtifactError,
    applied_subset_contrast,
    asymmetry_audit,
    build_analysis,
    contrast_from_counts,
    mechanism_stats,
    pooled_counts,
    verdict,
)

# ─── 定案值对照（QuixBugs pilot，2026-10-14，n=50） ───


def test_contrast_from_counts_reproduces_pilot_values() -> None:
    """pilot 的 7:1 不一致对、n=50 → δ=+12.00pp、p=0.0703（项目定案值）。"""
    counts = {"only_first": 7, "only_second": 1, "both": 21, "neither": 21}
    c = contrast_from_counts(counts)
    assert c["n_pairs"] == 50
    assert c["delta_pp"] == 12.0
    assert c["p_exact"] == 0.0703
    assert c["discordant"] == 8
    # BF10 应方向明确支持 H1（Jeffreys 标签：>3 中等支持）
    assert c["bf10"]["bf10_jeffreys"] > 3.0


def test_contrast_from_counts_zero_discordant_is_null() -> None:
    """无不一致对：δ=0、p=1.0、MDE/所需配对数不可计算（设计无鉴别力）。"""
    c = contrast_from_counts({"only_first": 0, "only_second": 0, "both": 5, "neither": 5})
    assert c["delta_pp"] == 0.0
    assert c["p_exact"] == 1.0
    assert c["mde_pp"] is None
    assert c["required_pairs_for_8pp"] is None


# ─── 预注册判定规则边界 ───


@pytest.mark.parametrize(
    ("p", "delta", "expected"),
    [
        (0.01, 12.0, "confirmed"),  # p<0.05 且 δ≥8pp
        (0.04, 8.0, "confirmed"),  # 边界：δ 恰达阈值
        (0.01, 7.9, "not_confirmed"),  # δ 不足（即便 p 很小）
        (0.07, 12.0, "trend"),  # 0.05≤p<0.10 且 δ>0
        (0.07, -3.0, "not_confirmed"),  # 趋势区间但方向为负
        (0.20, 12.0, "not_confirmed"),  # 功效不足
        (0.01, -15.0, "not_confirmed"),  # 显著负向
    ],
)
def test_verdict_prereg_boundaries(p: float, delta: float, expected: str) -> None:
    assert verdict({"p_exact": p, "delta_pp": delta}) == expected


def test_verdict_indeterminate_on_missing_stats() -> None:
    assert verdict({}) == "indeterminate"
    assert verdict({"p_exact": None, "delta_pp": None}) == "indeterminate"


def test_pilot_counts_verdict_is_trend() -> None:
    """pilot（p=0.0703, δ=+12pp）按预注册规则记 trend（与报告表述一致）。"""
    assert verdict({"p_exact": 0.0703, "delta_pp": 12.0}) == "trend"


# ─── 池化纪律：跨种子 task_id 错配防护 ───


def test_pooled_counts_sums_components_without_cross_seed_pairing() -> None:
    """池化只合计四种计数值；两种子 task_id 相同也绝不错配成对。"""
    seed_a = {"only_first": 3, "only_second": 1, "both": 10, "neither": 20}
    seed_b = {"only_first": 2, "only_second": 4, "both": 8, "neither": 15}
    pooled = pooled_counts([seed_a, seed_b])
    assert pooled["only_first"] == 5
    assert pooled["only_second"] == 5
    assert pooled["both"] == 18
    assert pooled["neither"] == 35
    assert pooled["n_pairs"] == 63
    assert pooled["discordant"] == 10
    # δ = (5−5)/63 = 0
    assert contrast_from_counts(pooled)["delta_pp"] == 0.0


# ─── 机制统计与审计 ───


def test_mechanism_stats_ignores_none_and_computes_means() -> None:
    rows = [
        {
            "spec_replace_applied": "attempted_replaced",
            "spec_expr_coverage": 0.8,
            "spec_compile_rate": 1.0,
            "detection_rate": 1.0,
        },
        {
            "spec_replace_applied": "attempted_replaced",
            "spec_expr_coverage": 0.4,
            "spec_compile_rate": 0.0,
            "detection_rate": 0.0,
        },
        {
            "spec_replace_applied": "attempted_fallback",
            "spec_expr_coverage": None,
            "spec_compile_rate": None,
            "detection_rate": None,
        },
    ]
    m = mechanism_stats(rows)
    assert m["n_rows"] == 3
    assert m["spec_replace_applied"] == {"attempted_replaced": 2, "attempted_fallback": 1}
    assert m["fallback_rate"] == pytest.approx(0.3333)
    assert m["spec_expr_coverage_mean"] == pytest.approx(0.6)
    assert m["spec_expr_coverage_n"] == 2
    assert m["spec_compile_rate_mean"] == pytest.approx(0.5)
    assert m["detection_available"] == 2
    assert m["detection_positive"] == 1
    assert m["detection_marginal"] == pytest.approx(0.5)


def test_mechanism_stats_empty_rows() -> None:
    m = mechanism_stats([])
    assert m["n_rows"] == 0
    assert m["fallback_rate"] is None
    assert m["spec_expr_coverage_mean"] is None
    assert m["detection_marginal"] is None


def test_asymmetry_audit_flags_arm_divergent_application() -> None:
    replace_rows = [
        {"task_id": "t1", "spec_replace_applied": "attempted_replaced"},
        {"task_id": "t2", "spec_replace_applied": "attempted_replaced"},
    ]
    specir_rows = [
        {"task_id": "t1", "spec_replace_applied": "attempted_replaced"},
        {"task_id": "t2", "spec_replace_applied": "attempted_fallback"},  # 不对称
    ]
    audit = asymmetry_audit(replace_rows, specir_rows)
    assert audit["n_compared"] == 2
    assert audit["n_asymmetric"] == 1
    assert audit["asymmetric_task_ids"] == ["t2"]


def test_asymmetry_audit_clean_when_symmetric() -> None:
    rows = [{"task_id": "t1", "spec_replace_applied": "attempted_fallback"}]
    audit = asymmetry_audit(rows, rows)
    assert audit["n_asymmetric"] == 0


def test_applied_subset_contrast_drops_fallback_tasks() -> None:
    replace_rows = [
        {"task_id": "t1", "spec_replace_applied": "attempted_replaced", "detection_rate": 0.0},
        {"task_id": "t2", "spec_replace_applied": "attempted_fallback", "detection_rate": 1.0},
        {"task_id": "t3", "spec_replace_applied": "attempted_replaced", "detection_rate": 0.0},
    ]
    specir_rows = [
        {"task_id": "t1", "spec_replace_applied": "attempted_replaced", "detection_rate": 1.0},
        {"task_id": "t2", "spec_replace_applied": "attempted_fallback", "detection_rate": 0.0},
        {"task_id": "t3", "spec_replace_applied": "attempted_replaced", "detection_rate": 0.0},
    ]
    c = applied_subset_contrast(replace_rows, specir_rows)
    # 仅 t1/t3 进入（t2 兩臂回退被剔除）；t1 仅 specir 检出
    assert c["n_pairs"] == 2
    assert c["only_first"] == 1
    assert c["only_second"] == 0
    assert c["delta_pp"] == 50.0


# ─── 集成：build_analysis 的跨种子防护与 provenance 校验 ───


def _write_batch(
    directory: Path,
    *,
    seed: int,
    spec_ir: bool,
    rows: list[dict],
    fingerprint: str = "aeb56401ca74e127821c4f9126dcb669",
) -> None:
    """写一个最小批次工件（results.aitester.details + provenance）。"""
    directory.mkdir(parents=True, exist_ok=True)
    batch = {
        "dataset": "synthetic",
        "seed": seed,
        "total_tasks": len(rows),
        "results": {
            "aitester": {
                "details": rows,
                "token_metrics": {
                    "total_tokens": 1000,
                    "total_llm_calls": 10,
                    "total_cache_hits": 0,
                },
            }
        },
        "provenance": {
            "profile": None,
            "seed": seed,
            "model_fingerprint": {"system_fingerprint": fingerprint, "pinned": True},
            "env_snapshot": {
                "DETECTION_SPEC_MODE": "replace",
                "SPEC_IR_ENABLE": "true" if spec_ir else None,
                "SPEC_IR_DSL_ENABLE": "true" if spec_ir else None,
                "AITESTER_CACHE_NAMESPACE": f"test_ns_{seed}_{'specir' if spec_ir else 'replace'}",
            },
        },
    }
    (directory / "benchmark_synthetic_test.json").write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")


def _row(task_id: str, det: float | None, applied: str = "attempted_replaced") -> dict:
    return {
        "task_id": task_id,
        "detection_rate": det,
        "spec_replace_applied": applied,
        "spec_expr_coverage": 0.5 if applied == "attempted_replaced" else None,
        "spec_compile_rate": 1.0 if applied == "attempted_replaced" else None,
    }


def _make_batch_dir(tmp_path: Path) -> Path:
    """构造 2 种子 × 2 臂工件；两种子 task_id 故意相同（错配陷阱）。"""
    batch_dir = tmp_path / "emse_specexpr_synth_test"
    # seed45：t1 仅 specir 检出；t2 仅 replace 检出；t3 双中；t4 双未
    _write_batch(
        batch_dir / "s45_replace",
        seed=45,
        spec_ir=False,
        rows=[_row("t1", 0.0), _row("t2", 1.0), _row("t3", 1.0), _row("t4", 0.0)],
    )
    _write_batch(
        batch_dir / "s45_specir",
        seed=45,
        spec_ir=True,
        rows=[_row("t1", 1.0), _row("t2", 0.0), _row("t3", 1.0), _row("t4", 0.0)],
    )
    # seed46：同 task_id 不同模式——t1 双中；t2 双未；t3 仅 specir；t4 仅 replace
    _write_batch(
        batch_dir / "s46_replace",
        seed=46,
        spec_ir=False,
        rows=[_row("t1", 1.0), _row("t2", 0.0), _row("t3", 0.0), _row("t4", 1.0)],
    )
    _write_batch(
        batch_dir / "s46_specir",
        seed=46,
        spec_ir=True,
        rows=[_row("t1", 1.0), _row("t2", 0.0), _row("t3", 1.0), _row("t4", 0.0)],
    )
    return batch_dir


def test_build_analysis_pools_within_seed_only(tmp_path: Path) -> None:
    """集成：跨种子 task_id 相同也必须在种子内配对，池化=各种子分量和。"""
    analysis = build_analysis(_make_batch_dir(tmp_path))
    pooled = analysis["primary_pooled"]
    # 若跨种子错配：t1(45:1,0 / 46:1,1)... 会得到不同计数；正确结果：
    assert pooled["n_pairs"] == 8
    assert pooled["only_specir"] == 2  # seed45.t1 + seed46.t3
    assert pooled["only_replace"] == 2  # seed45.t2 + seed46.t4
    assert pooled["both"] == 2
    assert pooled["neither"] == 2
    assert pooled["delta_pp"] == 0.0
    assert analysis["provenance_ok"] is True
    assert analysis["asymmetry_total"] == 0
    # 单种子分量可独立复算
    s45 = next(s for s in analysis["per_seed"] if s["seed"] == 45)
    assert s45["contrast"]["only_first"] == 1
    assert s45["contrast"]["only_second"] == 1
    assert s45["contrast"]["n_pairs"] == 4


def test_build_analysis_flags_dirty_provenance(tmp_path: Path) -> None:
    """replace 臂误开 SPEC_IR_ENABLE → provenance 校验必须失败。"""
    batch_dir = _make_batch_dir(tmp_path)
    _write_batch(
        batch_dir / "s45_replace",
        seed=45,
        spec_ir=True,  # 对照臂不应开启 SPEC_IR
        rows=[_row("t1", 0.0), _row("t2", 1.0), _row("t3", 1.0), _row("t4", 0.0)],
    )
    analysis = build_analysis(batch_dir)
    assert analysis["provenance_ok"] is False


def test_build_analysis_missing_artifact_raises_readable_error(tmp_path: Path) -> None:
    """工件缺失 → MissingArtifactError（消息含目录路径，可读诊断）。"""
    with pytest.raises(MissingArtifactError, match="s45_replace"):
        build_analysis(tmp_path / "nonexistent_dir")


def test_verdict_constants_match_prereg() -> None:
    """预注册阈值常量与文档一致（防漂移）。"""
    assert (CONFIRM_P, CONFIRM_DELTA_PP, TREND_P) == (0.05, 8.0, 0.10)
