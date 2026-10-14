"""M4：QuixBugs SpecExpr 扩样确认性分析脚本的回归测试（2026-10-14）。

覆盖 experiments/emse_quixbugs_specir_expand.py 的纯函数纪律：
  - McNemar 配对标准口径（双方 detection 非 None，与 pilot n=35/6:1 定案值对齐）；
  - 判定规则边界（confirmed / trend / not_confirmed）；
  - 贝叶斯因子数值性质（对称=1.0 / 单侧偏大）；
  - MDE 保守近似（n=0 → inf）；
  - provenance 校验（4 臂 namespace 互异 / 重复检测）；
  - 工件缺失的可读诊断（MissingArtifactError）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.emse_quixbugs_specir_expand import (
    MissingArtifactError,
    bayes_factor_10,
    build_analysis,
    mcnemar_contrast,
    mcnemar_exact_p,
    mde_two_proportion,
    verdict,
    verify_provenance,
)

# ─── McNemar 定案值对照（pilot 标准口径 6:1 / n=35 / δ=+14.29pp / p=0.125）──

def test_mcnemar_exact_p_symmetric() -> None:
    """b_pos==b_neg → p=1.0（无差异）。"""
    assert mcnemar_exact_p(0, 0) == 1.0
    assert mcnemar_exact_p(3, 3) == 1.0


def test_mcnemar_exact_p_pilot_value() -> None:
    """pilot 标准口径 6:1 / n=35 → δ=+14.29pp，p≈0.125（与 §6.7 定案值对齐）。"""
    # b_pos=6（specir 仅检出）, b_neg=1（NL 仅检出）
    p = mcnemar_exact_p(6, 1)
    delta = (6 - 1) / 35 * 100
    assert round(delta, 2) == 14.29  # pilot 定案 δ
    assert 0.10 < p < 0.15  # pilot 定案 p≈0.125（区间断言，防浮点漂移）


def test_bf10_symmetric_is_one() -> None:
    """完全对称（b_pos==b_neg）→ BF10=1.0。"""
    assert bayes_factor_10(0, 0) == 1.0
    assert bayes_factor_10(3, 3) == 1.0


def test_bf10_one_sided_direction() -> None:
    """单侧偏的 BF10 方向：b_pos>b_neg（specir 占优）→ BF10>1；
    b_neg>b_pos（NL 占优）→ BF10>1（对"处理组占优"假设而言偏向 H1 的对侧，
    数值上同样 >1——因为 BF10 度量的是"不一致对偏离 0.5"的证据强度，
    方向由 delta_pp 符号另行承载，BF10 本身不编码方向）。"""
    assert bayes_factor_10(6, 1) > 1.0
    assert bayes_factor_10(1, 6) > 1.0  # 对称性：|偏离| 相同 → 数值相同
    # 对称性精确核对（同一 |偏离|）
    assert abs(bayes_factor_10(6, 1) - bayes_factor_10(1, 6)) < 1e-9


def test_mde_positive_and_decreasing_in_n() -> None:
    """MDE 为正且随 n 增大而减小；n=0 → inf。"""
    assert mde_two_proportion(0) == float("inf")
    mde_35 = mde_two_proportion(35)
    mde_70 = mde_two_proportion(70)
    assert mde_35 > mde_70 > 0
    assert isinstance(mde_35, float)


# ─── 判定规则边界 ───────────────────────────────────────────────────────

def test_verdict_confirmed_boundary() -> None:
    """p<0.05 ∧ δ≥8pp = confirmed。"""
    assert verdict({"p_value": 0.03, "delta_pp": 10.0}) == "confirmed"
    assert verdict({"p_value": 0.04, "delta_pp": 8.0}) == "confirmed"
    # δ 恰 8pp 边界（≥ 含等号）
    assert verdict({"p_value": 0.01, "delta_pp": 8.0}) == "confirmed"


def test_verdict_trend() -> None:
    """p<0.10 ∧ δ>0 = trend（confirmed 条件不满足时）。"""
    assert verdict({"p_value": 0.08, "delta_pp": 5.0}) == "trend"  # δ<8 → 非 confirmed
    assert verdict({"p_value": 0.06, "delta_pp": 3.0}) == "trend"  # δ>0 且 p<0.1


def test_verdict_not_confirmed() -> None:
    """其余 = not_confirmed（δ≤0 或 p≥0.10）。"""
    assert verdict({"p_value": 0.15, "delta_pp": 10.0}) == "not_confirmed"  # p≥0.10
    assert verdict({"p_value": 0.03, "delta_pp": 0.0}) == "not_confirmed"  # δ≤0
    assert verdict({"p_value": 1.0, "delta_pp": -1.0}) == "not_confirmed"  # 负效应


def test_verdict_pilot_values_are_not_confirmed() -> None:
    """pilot 定案值（δ=+14.29pp, p=0.125）→ not_confirmed（p≥0.10 边界外）。

    注：pilot p=0.125 超出 TREND_P=0.10 边界，故按预注册规则判
    not_confirmed（功效不足需扩样）——这与预注册 §3 判定规则一致，
    也构成 M4 扩样的方法论动机（把 n 从 35 扩到 ≥70 以把 p 压到
    0.10 以内）。
    """
    assert verdict({"p_value": 0.125, "delta_pp": 14.29}) == "not_confirmed"
    # 边界核对：p 恰 0.10 内且 δ>0 → trend
    assert verdict({"p_value": 0.099, "delta_pp": 14.29}) == "trend"


# ─── mcnemar_contrast 纯函数 ────────────────────────────────────────────

def _mk_rows(mapping: dict[str, float | None]) -> dict[str, dict]:
    return {
        tid: {"detection_rate": det, "spec_replace_applied": "attempted_replaced",
              "spec_compile_rate": 0.5}
        for tid, det in mapping.items()
    }


def test_mcnemar_contrast_standard_caliber() -> None:
    """标准口径：双方 detection 非 None 的有效配对；None 行不进分母。"""
    specir = _mk_rows({"t1": 1.0, "t2": 0.0, "t3": None, "t4": 1.0})
    nl = _mk_rows({"t1": 0.0, "t2": 0.0, "t3": 0.0, "t4": 0.0})
    # 有效配对 = t1(1v0) + t2(0v0) + t4(1v0) = 3（t3 因 specir None 剔除）
    c = mcnemar_contrast(specir, nl)
    assert c["n_pairs"] == 3
    assert c["b_pos_specir_only"] == 2  # t1, t4
    assert c["b_neg_nl_only"] == 0
    assert c["ratio"] == "2:0"


def test_mcnemar_contrast_no_overlap() -> None:
    """无 task_id 重叠 → n_pairs=0，delta=0，p=1.0。"""
    specir = _mk_rows({"a": 1.0})
    nl = _mk_rows({"b": 0.0})
    c = mcnemar_contrast(specir, nl)
    assert c["n_pairs"] == 0
    assert c["delta_pp"] == 0.0
    assert c["p_value"] == 1.0


# ─── provenance 校验 ────────────────────────────────────────────────────

def _write_arm(tmp_path: Path, name: str, cache_ns: str) -> Path:
    p = tmp_path / f"{name}.json"
    payload = {"results": {"aitester": {"details": [
        {"task_id": "quixbugs__x", "detection_rate": 1.0,
         "spec_replace_applied": "attempted_replaced", "spec_compile_rate": 0.5},
    ]}}, "provenance": {"cache_namespace": cache_ns}}
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_verify_provenance_all_distinct(tmp_path: Path) -> None:
    """4 臂 cache namespace 互异 → ok=True。"""
    paths = {
        "specir": _write_arm(tmp_path, "specir", "ns_a"),
        "nl": _write_arm(tmp_path, "nl", "ns_b"),
        "specir_repeat": _write_arm(tmp_path, "specir_repeat", "ns_c"),
        "nl_repeat": _write_arm(tmp_path, "nl_repeat", "ns_d"),
    }
    res = verify_provenance(paths)
    assert res["ok"] is True
    assert res["duplicate"] == []


def test_verify_provenance_duplicate_detected(tmp_path: Path) -> None:
    """两臂共享同一 cache namespace → ok=False + duplicate 列出。"""
    paths = {
        "specir": _write_arm(tmp_path, "specir", "ns_same"),
        "nl": _write_arm(tmp_path, "nl", "ns_same"),
        "specir_repeat": _write_arm(tmp_path, "specir_repeat", "ns_c"),
        "nl_repeat": _write_arm(tmp_path, "nl_repeat", "ns_d"),
    }
    res = verify_provenance(paths)
    assert res["ok"] is False
    assert res["duplicate"] == ["ns_same"]


# ─── 工件缺失诊断 ───────────────────────────────────────────────────────

def test_build_analysis_missing_artifact(tmp_path: Path) -> None:
    """缺失臂 → MissingArtifactError（可读诊断，非裸 KeyError）。"""
    with pytest.raises(MissingArtifactError):
        build_analysis(tmp_path / "missing.json", tmp_path / "nl.json")


def test_build_analysis_two_arm(tmp_path: Path) -> None:
    """2 臂（无复跑）→ primary + verdict，无 repeat/merged 键。"""
    sp = _write_arm(tmp_path, "specir", "ns_a")
    nl = _write_arm(tmp_path, "nl", "ns_b")
    res = build_analysis(sp, nl)
    assert "primary" in res and "verdict" in res
    assert "repeat" not in res and "merged" not in res
