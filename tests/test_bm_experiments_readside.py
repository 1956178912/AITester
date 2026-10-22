"""BM（2026-10-22）：实验/报告读侧把"检测没发生 / 检测崩了"折成最有利判定 —— 收口锁。

缺陷族（BH→BL 系列第 5 面）。BL 只把双读口径接进 `src/`，登记边界写明
`experiments/` 未做——本轮就是那块。改前实测（Python 3.14.6，零 LLM）：

1. **崩溃腿折成最有利档**：`_compute_contamination_risk_level` 的
   `except Exception: return "low"` 在 15 条输入栅格上 **5 条命中**（bytes /
   list / dict / int / 黄金侧非 str），5/5 返回 `"low"`；`sys.modules` 投毒
   让导入腿失败，同样返回 `"low"`。10 条 str 对抗形状 **0 命中**——
   `_TOKEN_RE` 只保留标识符与数字，`ast.parse` 至多抛 SyntaxError 且被内层
   自己捕获，故 str 侧不可达（登记为"人工栅格 5 条 + 归档 0 实例"）。
   内层 `_combined_risk_level` 早在 O22 就引入 `unknown` 并写明"此前缺 patch /
   缺 gold / 异常时一律 fail-open 归 low"，包装器是这处修漏的最后一个站点。
2. **`contract_status` 在实验侧写了没人读**：结果行写（`run_benchmark.py:1872`）、
   状态声明（`state.py:371`）、节点发布（`nodes.py:2867`）三处都有，但
   `_build_risk_summary_for_result` 调 `build_risk_summary` 时不传它
   ⇒ BL 的 `contract_unmeasurable(...)` 披露在实验侧永不出现，
   `risk_summary["contract_status"]` 恒 None。
3. **R4/N1 用全行分母**：11197 行归档里 `regression_rate` **可测 0 行**
   （8012 None + 3185 缺键），而**带** P2P 材料的 184 行恰好全是缺键行
   ⇒ 现口径恒打印 `0.0%`（被读成"零回归"）；`test_error_rate` 可测
   7206/11197，现口径 7.3% vs 可测口径 11.3%（`single_agent` 6.7% vs 94.0%）。
   同一打印块里的 M1 三指标早已用"可测 m1_denom/n"，R4/N1 却用 `n`。
4. **5.3 对照表整行吞掉 medium/unknown/not_applicable**：表里没有任何计数，
   读者无从知道 high-vs-low 对照建立在几行之上。

修复口径：**不入最有利组，不改判定方向**。崩溃 ⇒ `unknown`（两个消费侧早已
把它排除在干净/污染两组分母之外）；比率 ⇒ 可测分母 + 显式"不可测"标注；
报告 ⇒ 加"未入对照任务"列。历史读数零变化判据：8865 行
`contamination_risk_level` 中非 str 补丁 0 行（崩溃腿 0 实例）、`unknown`
0 行 ⇒ 取值变更不触及任何已发布数字。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
from experiments.analysis_parts.cross_analysis import _contamination_cross_analysis
from experiments.run_benchmark import _build_risk_summary_for_result, _compute_contamination_risk_level
from experiments.run_main_batch import _print_r4_summary
from experiments.statistical_analysis import contamination_view_summary

ROOT = Path(__file__).resolve().parents[1]

_GOLDEN = "+def f(x):\n+    return x + 1\n"


def _wrap(generated: Any, golden: Any = _GOLDEN) -> str:
    return _compute_contamination_risk_level({"task_id": "t1", "patch": generated}, {"t1": golden})


# ─── 一、崩溃腿不再折成最有利档 ──────────────────────────────────────────


class TestCrashLegIsNotTheFavorableGrade:
    @pytest.mark.parametrize(
        "generated",
        [
            b"+def f(x):\n+    return x\n",  # bytes：line[0] 是 int，内层 TypeError
            ["+def f(): pass"],  # list：无 splitlines
            {"patch": "+x"},  # dict：无 splitlines
            123,  # int：无 splitlines
            1.5,  # float：无 splitlines
        ],
    )
    def test_non_str_patch_is_unknown_not_low(self, generated: Any) -> None:
        # 改前这 5 条全部返回 "low"（= 进 statistical_analysis 的"干净组"分母）
        assert _wrap(generated) == "unknown"

    def test_non_str_golden_side_is_unknown(self) -> None:
        assert _wrap("+x = 1\n", ["+x = 1\n"]) == "unknown"

    def test_import_leg_is_unknown(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "experiments.contamination_check", None)
        assert _wrap("+x = 1\n") == "unknown"

    @pytest.mark.parametrize(
        "generated",
        [
            _GOLDEN,  # 与黄金逐字相同 → high（检测真发生了）
            "+x = '\ud800'\n",  # 单落单 surrogate
            "+x = \x00\n",  # NUL 字节
            "```python\n+def f(): pass\n```",  # fenced 代码块
            "diff --git a/b.py b/b.py\nindex 1..2\n@@ -1 +1 @@\n-a\n+b\n",  # 真 git diff
            "+foo(" + "(" * 5000 + ")" * 5000 + ")\n",  # 深嵌套
            "+" + "a" * 20000 + "\n",  # 超长单 token
            "+x = 0755\n",  # 前导零数字字面量
        ],
    )
    def test_str_shapes_never_fold_into_unknown(self, generated: str) -> None:
        """str 侧不可达 ⇒ 一条都不该落到 unknown（防空腿被改成"崩了就逃"）。"""
        assert _wrap(generated) in ("high", "medium", "low")

    def test_str_with_no_overlap_still_means_clean(self) -> None:
        """ "检测过且无重叠证据"仍是 low —— 本轮只把"没测成"从 low 里摘出来。"""
        assert _wrap("+def unrelated():\n+    pass\n", golden="+class Zeta:\n+    zzz = 9\n") == "low"

    def test_missing_material_still_not_applicable(self) -> None:
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": "p"}, None) == "not_applicable"
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": ""}, {"t1": _GOLDEN}) == "not_applicable"


# ─── 二、unknown 落在诚实桶里（两个消费侧早已排除）──────────────────────


class TestUnknownLandsInAnHonestBucket:
    def test_statistical_view_excludes_unknown_from_both_denominators(self) -> None:
        data = {
            "a": [
                {"contamination_risk_level": "low", "passed": False},
                {"contamination_risk_level": "unknown", "passed": True},
                {"contamination_risk_level": "not_applicable", "passed": True},
            ]
        }
        s = contamination_view_summary(data)["a"]
        assert s["counts"] == {"high": 0, "medium": 0, "low": 1, "unknown": 1, "not_applicable": 1}
        # 干净组只有那 1 行 low ⇒ 崩溃行没有被算进 clean_n
        assert s["clean_passed_rate"] == 0.0
        assert s["contaminated_passed_rate"] is None

    def test_cross_analysis_buckets_unknown_outside_the_delta(self) -> None:
        details = [
            {"passed": True, "contamination_risk_level": "high"},
            {"passed": False, "contamination_risk_level": "low"},
            {"passed": True, "contamination_risk_level": "unknown"},
        ]
        result = _contamination_cross_analysis(details)
        assert result["by_risk_level"]["unknown"]["tasks"] == 1
        assert result["high_vs_low_success_delta"] == pytest.approx(1.0 - 0.0)

    def test_report_table_discloses_uncompared_rows(self) -> None:
        rows = [
            {"task_id": "t1", "passed": True, "contamination_risk_level": "high"},
            {"task_id": "t2", "passed": False, "contamination_risk_level": "low"},
            {"task_id": "t3", "passed": True, "contamination_risk_level": "unknown"},
            {"task_id": "t4", "passed": True, "contamination_risk_level": "not_applicable"},
            {"task_id": "t5", "passed": False, "contamination_risk_level": "medium"},
        ]
        md = ar_mod.render_markdown(
            ar_mod.build_analysis({"dataset": "demo", "results": {"b": {"details": rows, "success_rate": 60.0}}}),
            "demo.json",
        )
        assert "| 成功率差（高-低） | 未入对照任务 |" in md
        assert "| b | 1 | 1.0 | 1 | 0.0 | 1.0000 | 3 |" in md
        assert "未入对照任务」= medium/unknown/not_applicable" in md


# ─── 三、contract_status 走到实验侧风险摘要 ─────────────────────────────


class TestContractStatusReachesExperimentSide:
    def test_disabled_branch_forwards_status(self, monkeypatch) -> None:
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        summary = _build_risk_summary_for_result({"patch": "+x = 1\n", "contract_status": "error"})
        assert summary["enabled"] is False
        assert summary["contract_status"] == "error"

    def test_enabled_branch_adds_disclosure_without_changing_the_score(self, monkeypatch) -> None:
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        state = {"patch": "+x = 1\n", "contract_status": "error", "contract_missing_symbols": []}
        summary = _build_risk_summary_for_result(state)
        assert summary["contract_status"] == "error"
        assert any(r.startswith("contract_unmeasurable(error)") for r in summary["reasons"])
        # 判定不变：同输入但 status=ok 的分/级逐位相同（只多一条披露）
        ok = _build_risk_summary_for_result({**state, "contract_status": "ok"})
        assert summary["risk_score"] == ok["risk_score"]
        assert summary["risk_level"] == ok["risk_level"]
        assert summary["factors"] == ok["factors"]
        assert not any(r.startswith("contract_unmeasurable(") for r in ok["reasons"])

    def test_missing_symbols_signal_still_dominates(self, monkeypatch) -> None:
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        summary = _build_risk_summary_for_result(
            {"patch": "+x = 1\n", "contract_status": "error", "contract_missing_symbols": ["foo"]}
        )
        assert any(r.startswith("contract_missing(1)") for r in summary["reasons"])
        assert not any(r.startswith("contract_unmeasurable(") for r in summary["reasons"])

    def test_failure_branch_keeps_none(self, monkeypatch) -> None:
        """失败分支没有 final_state ⇒ None = "这条腿本轮没做"，不等于 ok。"""
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        assert _build_risk_summary_for_result(None)["contract_status"] is None


# ─── 四、R4/N1 用可测分母并披露 k/n ─────────────────────────────────────


def _batch(tmp_path: Path, details: list[dict[str, Any]]) -> Path:
    p = tmp_path / "batch.json"
    p.write_text(json.dumps({"results": {"b": {"details": details}}}), encoding="utf-8")
    return p


class TestMeasurableDenominators:
    def test_unmeasurable_rows_are_not_scored_as_zero_regression(self, tmp_path: Path, capsys) -> None:
        details = [
            {"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 0.0},
            {"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 0.0},
            {"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 0.0},
        ]
        details[0]["regression_rate"] = None  # 没测成
        details[1]["test_error_rate"] = None  # 没测成
        details[2]["test_error_rate"] = 1.0  # 唯一可测且为 1.0
        _print_r4_summary(_batch(tmp_path, details))
        out = capsys.readouterr().out
        # 改前：regr 0.0%（读成"零回归"）、te 33.3%（把 2 行未测当"没错"）
        assert "R4 regression_rate=不可测（无可测行）（可测 0/3）" in out
        assert "N1 test_error_rate=100.0%（可测 1/3）" in out

    def test_measurable_rate_divides_by_measurable_rows(self, tmp_path: Path, capsys) -> None:
        details = [
            {"regression_rate": 1.0, "test_error_rate": 0.0},
            {"regression_rate": 0.0, "test_error_rate": 0.0},
            {"regression_rate": None, "test_error_rate": None},
            {"regression_rate": None, "test_error_rate": None},
        ]
        _print_r4_summary(_batch(tmp_path, details))
        out = capsys.readouterr().out
        assert "R4 regression_rate=50.0%（可测 2/4）" in out
        assert "N1 test_error_rate=0.0%（可测 2/4）" in out

    def test_missing_key_counts_as_unmeasurable(self, tmp_path: Path, capsys) -> None:
        # 归档里 3185/11197 行连键都没有 —— 与 None 同判"不可测"
        _print_r4_summary(_batch(tmp_path, [{"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 1.0}]))
        out = capsys.readouterr().out
        assert "不可测（无可测行）" in out
        assert "可测 0/1" in out

    def test_m1_line_caliber_is_shared(self, tmp_path: Path, capsys) -> None:
        _print_r4_summary(_batch(tmp_path, [{"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 1.0}]))
        out = capsys.readouterr().out
        assert "M1 三指标（可测 1/1 任务）" in out
        assert "可测 0/1" in out  # 同块内 R4/N1 也用"可测 k/n"字样


# ─── 五、接线存在性锁（防节被误删）──────────────────────────────────────


class TestWiringLocks:
    def test_wrapper_no_longer_returns_the_favorable_grade_on_crash(self) -> None:
        src = (ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8")
        assert 'logger.debug("污染风险等级计算失败（标记 unknown，不入干净组）' in src
        assert 'return "unknown"' in src
        assert "计算失败（保守标记 low）" not in src

    def test_risk_summary_builder_forwards_status(self) -> None:
        import inspect

        from experiments.run_benchmark import _build_risk_summary_for_result as f

        body = inspect.getsource(f)
        assert 'contract_status=final_state.get("contract_status")' in body

    def test_report_section_declares_excluded_bucket(self) -> None:
        src = (ROOT / "experiments/analyze_results.py").read_text(encoding="utf-8")
        assert "未入对照任务" in src
        assert 'if lv not in ("high", "low")' in src

    def test_consumers_still_exclude_unknown(self) -> None:
        src = (ROOT / "experiments/statistical_analysis.py").read_text(encoding="utf-8")
        assert '"high": 0, "medium": 0, "low": 0, "unknown": 0, "not_applicable": 0' in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
