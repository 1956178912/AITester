#!/usr/bin/env python3
"""T-10 回归锁定：通过率混淆敏感性分析的确定性、口径与匹配语义。

三层锁定（对应 EMSE 审稿人 A3 的复核点）：
1. **匹配语义**：只保留"参照臂声明成功过"的 pattern×seed；未成功的 pattern
   必须落在 `unmatched` 对照组（防止匹配逻辑退化为"全量对比"）；
2. **口径纪律**：`detection_rate is None` 的行不进分母（不臆造 0），并同时给出
   None 计 0 的下界；
3. **确定性**：同参数重复运行输出逐字节一致（bootstrap 固定 seed=42）。

真实工件（三种子主批次）缺席时相关用例 `pytest.skip`（CI 精简环境）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments.pass_matched_sensitivity import (
    DEFAULT_OUT,
    PASS_MATCHED_BATCH_GLOB,
    conditioned_on_success,
    load_batches,
    main,
    pass_matched_subset,
    success_declaration_table,
    wilson_ci,
)

_MAIN_BATCH = Path("experiments/results/main_batch")
_HAS_ARTIFACTS = bool(sorted(_MAIN_BATCH.glob(PASS_MATCHED_BATCH_GLOB)))
_needs_artifacts = pytest.mark.skipif(not _HAS_ARTIFACTS, reason="三种子主批次工件不在工作树")


def _row(
    *,
    seed: int,
    pattern: str,
    passed: bool | None,
    detection: float | None,
    false_fix: float | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    # 真实行的 task_id 已由加载器加 `s<seed>__` 前缀（种子分层拼接）；测试夹具
    # 必须同构，否则 pattern×seed 匹配语义无法被检验（task_id 会跨种子碰撞）。
    task_id = f"s{seed}__synthetic__{task or f'task_{seed:04d}'}"
    return {
        "task_id": task_id,
        "_seed": seed,
        "_pattern": pattern,
        "passed": passed,
        "detection_rate": detection,
        "false_fix_rate": false_fix,
        "task_metadata": {"pattern_name": pattern, "difficulty": 1},
    }


class TestWilsonCI:
    def test_bounds_are_ordered_and_bracket_point_estimate(self):
        lo, hi = wilson_ci(38, 240)
        assert 0.0 <= lo < 38 / 240 < hi <= 1.0

    def test_degenerate_success_counts(self):
        lo, hi = wilson_ci(143, 143)
        # k == n：Wilson 上界在数值上收敛到 1（浮点可能为 0.9999999999999999），
        # 其定义域上界即 1.0，故用容差比较而非严格相等。
        assert lo > 0.95 and hi == pytest.approx(1.0)
        lo0, hi0 = wilson_ci(0, 261)
        assert lo0 == 0.0 and 0.0 < hi0 < 0.05

    def test_zero_denominator_is_not_a_fake_zero(self):
        import math

        lo, hi = wilson_ci(0, 0)
        assert math.isnan(lo) and math.isnan(hi)


class TestSuccessDeclarationAndConditional:
    def test_success_declaration_excludes_unmeasurable_rows(self):
        rows = {
            "armA": [
                _row(seed=42, pattern="p1", passed=True, detection=1.0),
                _row(seed=42, pattern="p2", passed=False, detection=0.0),
                _row(seed=42, pattern="p3", passed=None, detection=None),
            ]
        }
        table = success_declaration_table(rows, ["armA"])
        assert table[0]["passed_measurable"] == 2  # None 行不进分母
        assert table[0]["passed_true"] == 1
        assert table[0]["success_declaration_rate"] == pytest.approx(0.5)

    def test_conditional_false_fix_uses_passed_rows_only(self):
        rows = {
            "armA": [
                _row(seed=42, pattern="p1", passed=True, detection=1.0, false_fix=1.0),
                _row(seed=42, pattern="p2", passed=True, detection=0.0, false_fix=1.0),
                _row(seed=42, pattern="p3", passed=False, detection=0.0, false_fix=0.0),
            ]
        }
        cond = conditioned_on_success(rows, ["armA"])[0]
        assert cond["passed_rows"] == 2
        assert cond["false_fix_measurable"] == 2
        assert cond["false_fix_conditional_rate"] == pytest.approx(1.0)


class TestPassMatchedSemantics:
    def test_matched_subset_only_contains_reference_success_patterns(self):
        rows = {
            "plain_llm_df": [_row(seed=42, pattern="hit", passed=True, detection=1.0, task="t1")],
            "aitester": [
                _row(seed=42, pattern="hit", passed=False, detection=0.0, task="t1"),
                _row(seed=42, pattern="miss", passed=False, detection=1.0, task="t2"),
            ],
        }
        out = pass_matched_subset(rows, arm_treatment="aitester", arm_reference="plain_llm_df")
        assert out["reference_success_pattern_count"] == 1
        assert out["matched_strict"]["rows"] == 1
        assert out["matched_strict"]["detection_true"] == 0
        assert out["unmatched"]["rows"] == 1
        assert out["unmatched"]["detection_true"] == 1

    def test_matching_is_pattern_x_seed_not_pattern_only(self):
        """参照臂仅在 seed 42 成功 → seed 43 的同 pattern 不得进入严格匹配。"""
        rows = {
            "plain_llm_df": [_row(seed=42, pattern="hit", passed=True, detection=1.0, task="t1")],
            "aitester": [
                _row(seed=42, pattern="hit", passed=False, detection=0.0, task="t1"),
                _row(seed=43, pattern="hit", passed=False, detection=0.0, task="t1"),
            ],
        }
        out = pass_matched_subset(rows, arm_treatment="aitester", arm_reference="plain_llm_df")
        assert out["matched_strict"]["rows"] == 1  # 只含 seed 42
        assert out["matched_loose"]["rows"] == 2  # 宽松口径含 seed 43

    def test_none_detection_is_excluded_but_reported_as_lower_bound(self):
        rows = {
            "plain_llm_df": [_row(seed=42, pattern="hit", passed=True, detection=1.0, task="t1")],
            "aitester": [
                _row(seed=42, pattern="hit", passed=False, detection=None, task="t1"),
            ],
        }
        out = pass_matched_subset(rows, arm_treatment="aitester", arm_reference="plain_llm_df")
        assert out["matched_strict"]["detection_measurable"] == 0
        assert out["matched_strict"]["detection_rate"] is None
        assert out["matched_strict"]["detection_rate_none_as_zero"] == 0.0


@_needs_artifacts
class TestAgainstStoredArtifacts:
    def test_load_batches_pools_three_seeds(self):
        rows = load_batches(_MAIN_BATCH, seeds=(42, 43, 44))
        batches = rows.pop("__batches__")
        assert len(batches) == 3
        assert sorted(b["seed"] for b in batches) == [42, 43, 44]
        for arm in ("aitester", "plain_llm", "plain_llm_df"):
            assert len(rows[arm]) == 261

    def test_run_is_deterministic(self, tmp_path: Path):
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        for out in (out_a, out_b):
            assert main(["--results-dir", str(_MAIN_BATCH), "--out", str(out)]) == 0
        # 载荷内 `out` 字段与报告尾行记录输出路径（两份必然不同），剔除后比对。
        payload_a = json.loads(out_a.read_text(encoding="utf-8"))
        payload_b = json.loads(out_b.read_text(encoding="utf-8"))
        payload_a.pop("out")
        payload_b.pop("out")
        assert payload_a == payload_b
        md_a = out_a.with_suffix(".md").read_text(encoding="utf-8").splitlines()
        md_b = out_b.with_suffix(".md").read_text(encoding="utf-8").splitlines()
        assert md_a[:-1] == md_b[:-1]  # 末行为工件路径（预期不同）
        assert len(md_a) == len(md_b)

    def test_reported_headline_facts_match_artifact(self):
        """锚定三项已归档事实，防止口径漂移：成功声明率 2.68%、条件假修复 100%、匹配子集 0 检出。"""
        rows = load_batches(_MAIN_BATCH, seeds=(42, 43, 44))
        rows.pop("__batches__", None)
        sd = {r["arm"]: r for r in success_declaration_table(rows, ["aitester", "plain_llm", "plain_llm_df"])}
        assert sd["plain_llm_df"]["passed_true"] == 7
        assert sd["plain_llm_df"]["success_declaration_rate"] == pytest.approx(7 / 261)
        cond = {r["arm"]: r for r in conditioned_on_success(rows, ["aitester", "plain_llm", "plain_llm_df"])}
        assert cond["aitester"]["false_fix_conditional_rate"] == pytest.approx(1.0)
        matched = pass_matched_subset(rows, arm_treatment="aitester", arm_reference="plain_llm_df")
        assert matched["matched_strict"]["detection_true"] == 0
        assert matched["matched_strict"]["rows"] > 0
        # 工件路径常量指向 results 目录（避免误写到源码树）
        assert DEFAULT_OUT.name == "PASS_MATCHED.json"
        assert "results" in DEFAULT_OUT.parts

    def test_json_payload_has_caliber_header(self, tmp_path: Path):
        out = tmp_path / "p.json"
        assert main(["--results-dir", str(_MAIN_BATCH), "--out", str(out)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        for key in (
            "results_dir",
            "batches",
            "seeds",
            "arms",
            "rows_per_arm",
            "success_declaration",
            "conditioned_on_success",
            "pass_matched",
            "paired_detection_bootstrap",
        ):
            assert key in payload, key
        assert payload["rows_per_arm"] == 261
