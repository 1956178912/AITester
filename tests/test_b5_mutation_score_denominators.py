"""B5(a)（2026-11-05）：变异**得分段**必须带着自己的分母落盘。

缺陷形态（最小批实测）：同一行里 `mutation_score=1.0` 与 `mutants_killed=0` 并存。
两个变异评估段共写一行——

- 得分段 `_compute_mutation_scores_for_baseline`（判据 rc==1，对**缺陷码**变异）
  只写 `mutation_score`，它自己算出的 `mutants_killed`/`mutants_total` **只进日志**；
- 检出段 `_compute_mutation_detection_for_baseline`（行为差异判据，对 **gold fixed**
  变异）写 `mutants_killed`/`mutants_total`，且缺 gold 材料时整段跳过并写 0/0 占位。

于是工件里那对 0/0 说的是"检出段没材料"，与 1.0 那个分母毫无关系；任何按
`killed/total` 复算得分、或拿计数交叉校验得分的分析，对这些行都是错的。
本文件锁三件事：① 得分段用自己的键名落分母，**不碰**检出段的键；
② 跳过腿记 None 而不是 0（"没跑到"不得写成一个可被求和的零分母）；
③ 得分与分母在同一次计算里恒等（`score == killed/total`）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import experiments.run_benchmark as rb


class _Task:
    def __init__(self, task_id: str = "synthetic__mod", instance_code: str = "def f():\n    return 1\n") -> None:
        self.task_id = task_id
        self.instance_code = instance_code
        self.metadata: dict[str, Any] = {"source": "synthetic"}


def _row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": "synthetic__mod", "generated_test": "def test_f():\n    assert f() == 1\n"}
    row.update(extra)
    return row


def _stub_score(monkeypatch: pytest.MonkeyPatch, ret: dict[str, Any]) -> MagicMock:
    spy = MagicMock(return_value=ret)
    # 得分段是函数体内延迟导入（`from experiments.mutation_testing import
    # compute_mutation_score`），因此桩必须打在**源模块**上才取得到
    import experiments.mutation_testing as mt

    monkeypatch.setattr(mt, "compute_mutation_score", spy)
    return spy


@pytest.mark.unit
class TestScorePassCarriesItsOwnDenominator:
    def test_measured_leg_writes_score_prefixed_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = _stub_score(
            monkeypatch,
            {"available": True, "mutation_score": 0.75, "mutants_killed": 3, "mutants_total": 4},
        )
        rows = [_row()]
        rb._compute_mutation_scores_for_baseline(rows, {"synthetic__mod": _Task()}, max_mutants=2)
        assert spy.call_count == 1
        r = rows[0]
        assert r["mutation_score"] == 0.75
        assert r["mutation_score_mutants_killed"] == 3
        assert r["mutation_score_mutants_total"] == 4
        assert r["mutation_score_available"] is True

    def test_score_pass_never_touches_detection_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """核心锁：检出段的 `mutants_killed`/`mutants_total` 归检出段所有。

        此前两段的证据挤在同一对键上，跳过腿的 0/0 会把得分段的真实计数盖掉
        （或反过来让 1.0 配着无关系的 0/0 落盘）。
        """
        _stub_score(
            monkeypatch,
            {"available": True, "mutation_score": 1.0, "mutants_killed": 5, "mutants_total": 5},
        )
        rows = [_row(mutants_killed=0, mutants_total=0, mutation_detection_rate=None)]
        rb._compute_mutation_scores_for_baseline(rows, {"synthetic__mod": _Task()}, max_mutants=2)
        r = rows[0]
        assert (r["mutants_killed"], r["mutants_total"]) == (0, 0), "得分段不得改写检出段的计数"
        assert (r["mutation_score_mutants_killed"], r["mutation_score_mutants_total"]) == (5, 5)
        assert r["mutation_score"] == 1.0

    @pytest.mark.parametrize(
        "row,task",
        [
            pytest.param(_row(generated_test=None), _Task(), id="无生成测试"),
            pytest.param(_row(), None, id="无任务映射"),
            pytest.param(_row(), _Task(instance_code=""), id="无被测源码"),
        ],
    )
    def test_skip_legs_record_none_not_zero(self, row: dict[str, Any], task: Any) -> None:
        """三条兜底路径都记 None：0 是"分母为零的可加数"，None 才是"这一段没跑"。"""
        rows = [row]
        tasks = {} if task is None else {task.task_id: task}
        rb._compute_mutation_scores_for_baseline(rows, tasks, max_mutants=2)
        r = rows[0]
        assert r["mutation_score"] is None
        assert r["mutation_score_mutants_killed"] is None
        assert r["mutation_score_mutants_total"] is None
        assert r["mutation_score_available"] is False

    def test_unavailable_pool_keeps_counts_visible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无变异体（available=False）：score=None，但计数仍是**真值** 0/0。

        "这一份源码没生成出变异体"是有信息的事实（分母确实为 0），
        与"这一段压根没跑"（None）必须能分辨。
        """
        _stub_score(
            monkeypatch,
            {"available": False, "mutation_score": None, "mutants_killed": 0, "mutants_total": 0},
        )
        rows = [_row()]
        rb._compute_mutation_scores_for_baseline(rows, {"synthetic__mod": _Task()}, max_mutants=2)
        r = rows[0]
        assert r["mutation_score"] is None
        assert r["mutation_score_available"] is False
        assert (r["mutation_score_mutants_killed"], r["mutation_score_mutants_total"]) == (0, 0)


@pytest.mark.unit
class TestScoreDenominatorIdentityOnRealMutants:
    """真跑一次变异评估：得分与分母必须来自同一次计算且恒等。"""

    def test_score_equals_killed_over_total(self) -> None:
        source = "def f(a):\n    return a + 1\n"
        test = "def test_f():\n    assert f(1) == 2\n\n\ndef test_f_again():\n    assert f(0) == 1\n"
        from experiments.mutation_testing import compute_mutation_score

        result = compute_mutation_score(
            source_code=source,
            test_code=test,
            module_file="/tmp/b5_placeholder_module.py",
            max_mutants=3,
        )
        total = int(result.get("mutants_total") or 0)
        killed = int(result.get("mutants_killed") or 0)
        assert total >= 1, f"轻量 AST 生成器对该源码应至少产出 1 个变异体，实为 {result}"
        assert result.get("available") is True
        assert result["mutation_score"] == round(killed / total, 4)


@pytest.mark.unit
class TestMetricsSchemaRegistration:
    """新键必须进 BASELINE 的 metrics_schema（缺登记即红，防工件字段静默漂移）。"""

    def test_score_denominators_are_registered(self) -> None:
        from pathlib import Path

        import yaml

        data = yaml.safe_load(Path("BASELINE.yaml").read_text(encoding="utf-8"))
        schema = data["benchmark"]["metrics_schema"]
        for key in (
            "mutation_score_mutants_killed",
            "mutation_score_mutants_total",
            "mutation_score_available",
        ):
            assert key in schema, f"{key} 未登记进 metrics_schema"
