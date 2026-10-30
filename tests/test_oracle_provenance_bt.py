"""BT 轮（2026-10-22）：验收 oracle 来源与可见性——写入端按真实验收路径取值，
报告端把两个只写不读的键读起来。

缺陷形态：`oracle_type` 恒为 `generated_test`、`test_visible_to_system` 硬编码
`True`；而 SWE-bench 仓库级验收的 `passed` 来自 gold FAIL_TO_PASS/PASS_TO_PASS
（`executor_repo.verify`），gold 测试对系统不可见——检查点把事实说反了。
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import experiments.run_benchmark as rb
from experiments._oracle_provenance import ORACLE_TYPE_REPO_GOLD
from experiments.statistical_analysis import oracle_provenance_stats, oracle_provenance_summary
from src.datasets.dataset_loader import BenchmarkTask

ROOT = Path(__file__).resolve().parents[1]


def _task(**metadata) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="django__django-1",
        repo_name="django/django",
        problem_statement="p",
        instance_code="def f():\n    return 1\n",
        test_code="",
        expected_pass_count=1,
        total_test_count=1,
        metadata=metadata,
    )


_REPO_META = {
    "source": "swe_bench",
    "fail_to_pass": ["tests/test_x.py::test_a"],
    "pass_to_pass": ["tests/test_x.py::test_b"],
    "repo_url": "https://example.com/repo.git",
    "base_commit": "0" * 40,
}


class TestOracleDescriptor:
    def test_repo_gold_arm_is_hidden(self, monkeypatch):
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        assert rb._oracle_descriptor(_task(**_REPO_META), "aitester", None) == (
            ORACLE_TYPE_REPO_GOLD,
            False,
        )

    def test_non_aitester_arm_uses_generated_test(self, monkeypatch):
        """同一 SWE-bench 任务，plain_llm 臂不走仓库级验收 → 生成测试 + 可见。"""
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        assert rb._oracle_descriptor(_task(**_REPO_META), "plain_llm", None) == ("generated_test", True)

    def test_repo_level_execution_disabled_falls_back(self, monkeypatch):
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", False)
        assert rb._oracle_descriptor(_task(**_REPO_META), "aitester", None) == ("generated_test", True)

    def test_synthetic_task_uses_generated_test(self, monkeypatch):
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        assert rb._oracle_descriptor(_task(source="synthetic"), "aitester", None) == ("generated_test", True)

    def test_enhanced_oracle_keeps_visibility(self, monkeypatch):
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        monkeypatch.setenv("ORACLE_ENHANCE_ENABLE", "true")
        state = {"oracle_enhanced": True}
        assert rb._oracle_descriptor(_task(source="synthetic"), "aitester", state) == (
            "enhanced_generated_test",
            True,
        )

    @pytest.mark.parametrize("term", ["source", "fail_to_pass", "repo_url", "base_commit"])
    def test_each_repo_material_term_stops_one_input(self, monkeypatch, term):
        """四个仓库材料条件各只有一个输入能让它转红——缺一即回落生成测试 + 可见。

        `source` 一档特意保留其余三件仓库材料：否则"少 source"这一档在任何
        合成任务上都与"少 fail_to_pass"同形，术语本身就没有独立可观测面。
        """
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        metadata = dict(_REPO_META)
        if term == "source":
            metadata["source"] = "synthetic"
        else:
            metadata.pop(term)
        assert rb._oracle_descriptor(_task(**metadata), "aitester", None) == ("generated_test", True)

    def test_task_without_metadata_falls_back(self, monkeypatch):
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        assert rb._oracle_descriptor(_task(), "aitester", None) == ("generated_test", True)

    def test_metadata_none_falls_back(self, monkeypatch):
        """加载器给出 `metadata=None` 时不得崩在取值上——兜底后仍是生成测试 + 可见。"""
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        task = _task(**_REPO_META)
        task.metadata = None
        assert rb._oracle_descriptor(task, "aitester", None) == ("generated_test", True)


class TestBuilderWritesDescriptor:
    def test_error_branch_writes_gold_hidden(self, monkeypatch):
        """崩溃行也必须声明它本该使用的 oracle（不能折成生成测试验收）。"""
        monkeypatch.setattr(rb, "REPO_LEVEL_EXECUTION", True)
        result = rb._build_task_result(
            _task(**_REPO_META),
            0.0,
            diagnosis="boom",
            error_category="error",
            oracle=(ORACLE_TYPE_REPO_GOLD, False),
        )
        assert result["oracle_type"] == ORACLE_TYPE_REPO_GOLD
        assert result["test_visible_to_system"] is False

    def test_default_keeps_historical_shape(self):
        result = rb._build_task_result(_task(source="synthetic"), 0.0, diagnosis="boom", error_category="error")
        assert (result["oracle_type"], result["test_visible_to_system"]) == ("generated_test", True)

    def test_default_fallback_still_asks_the_label_helper(self, monkeypatch):
        """`oracle=None` 的回落必须仍走 `_oracle_type_label`，不是写死常量。

        写死会让直接调用构造器的旧路径丢掉增强档（增强档与生成档在结果行同形）。
        """
        monkeypatch.setattr(rb, "_oracle_type_label", lambda _state: "label-was-called")
        result = rb._build_task_result(_task(source="synthetic"), 0.0, diagnosis="boom", error_category="error")
        assert result["oracle_type"] == "label-was-called"
        assert result["test_visible_to_system"] is True


class TestOracleProvenanceSummary:
    def test_repo_rows_require_gold_hidden(self):
        data = {
            "aitester": [
                {
                    "task_id": "t1",
                    "repo_verification": {"passed": True},
                    "oracle_type": ORACLE_TYPE_REPO_GOLD,
                    "test_visible_to_system": False,
                },
                # BT 修复前的形态：repo 行却标生成测试 + 可见
                {
                    "task_id": "t2",
                    "repo_verification": {"passed": True},
                    "oracle_type": "generated_test",
                    "test_visible_to_system": True,
                },
            ]
        }
        out = oracle_provenance_summary(data)["aitester"]

        assert out["repo_rows"] == 2
        assert out["repo_rows_unrecorded"] == 0
        assert out["repo_rows_consistent"] == 1
        assert out["n_violations"] == 1
        assert out["violations"] == ["t2"]
        assert out["consistent"] is False
        assert out["repo_rows_unrecorded"] + out["repo_rows_consistent"] + out["n_violations"] == out["repo_rows"]

    def test_repo_row_without_any_declaration_is_unrecorded(self):
        """归档实测形态：有仓库级验收、两键都缺席（早于 R52）——缺键不是错标。"""
        out = oracle_provenance_stats(
            [{"task_id": "legacy", "passed": True, "repo_verification": {"passed": False, "output": "x"}}]
        )

        assert out["repo_rows"] == 1
        assert out["repo_rows_unrecorded"] == 1
        assert out["repo_rows_consistent"] == 0
        assert out["n_violations"] == 0
        assert out["violations"] == []
        assert out["consistent"] is True

    @pytest.mark.parametrize("missing", ["oracle_type", "test_visible_to_system"])
    def test_half_declared_repo_row_is_incomplete_not_unrecorded(self, missing: str):
        """只记录一个键属不完整声明：仍计入不一致，不能折进「缺声明」。"""
        row = {
            "task_id": "t1",
            "repo_verification": {"passed": True},
            "oracle_type": ORACLE_TYPE_REPO_GOLD,
            "test_visible_to_system": False,
        }
        row.pop(missing)
        out = oracle_provenance_stats([row])

        assert out["repo_rows_unrecorded"] == 0
        assert out["n_violations"] == 1
        assert out["violations"] == ["t1"]

    def test_legacy_rows_are_not_recorded_not_violations(self):
        """R52 之前的批次没有这两个键：记未记录，不得判成"生成测试验收"。"""
        out = oracle_provenance_summary({"aitester": [{"task_id": "t0", "passed": True}]})["aitester"]

        assert out["by_type"] == {"not_recorded": 1}
        assert out["visibility"] == {"not_recorded": 1}
        assert out["n_violations"] == 0
        assert out["recorded_rows"] == 0

    def test_other_values_are_named(self):
        out = oracle_provenance_summary(
            {"aitester": [{"task_id": "t1", "oracle_type": "weird", "test_visible_to_system": True}]}
        )["aitester"]

        assert out["by_type"] == {"other": 1}
        assert out["other_values"] == {"weird": 1}

    def test_local_arm_is_visible(self):
        out = oracle_provenance_summary(
            {"aitester": [{"task_id": "t1", "oracle_type": "generated_test", "test_visible_to_system": True}]}
        )["aitester"]

        assert out["visibility"] == {"visible": 1}
        assert out["consistent"] is True

    def test_gold_and_enhanced_values_are_in_the_vocabulary(self):
        """词表缺一档，该档的行就被折进「词表外」——两档各钉一次。"""
        for value in ("gold_fail_to_pass", "enhanced_generated_test"):
            out = oracle_provenance_stats([{"task_id": "t1", "oracle_type": value}])
            assert out["by_type"] == {value: 1}
            assert out["other_values"] == {}

    def test_every_row_lands_in_exactly_one_bucket(self):
        rows = [
            {"task_id": "r1", "oracle_type": ORACLE_TYPE_REPO_GOLD, "test_visible_to_system": False},
            {"task_id": "r2", "oracle_type": "enhanced_generated_test", "test_visible_to_system": True},
            {"task_id": "r3", "oracle_type": "generated_test", "test_visible_to_system": True},
            {"task_id": "r4", "oracle_type": None, "test_visible_to_system": None},
            {"task_id": "r5"},
            {"task_id": "r6", "oracle_type": "weird", "test_visible_to_system": True},
            {"task_id": "r7", "oracle_type": 7, "test_visible_to_system": "false"},
        ]
        out = oracle_provenance_stats(rows)

        assert sum(out["by_type"].values()) == out["n_rows"] == len(rows)
        assert sum(out["visibility"].values()) == out["n_rows"]
        assert out["by_type"] == {
            ORACLE_TYPE_REPO_GOLD: 1,
            "enhanced_generated_test": 1,
            "generated_test": 1,
            "not_recorded": 2,
            "other": 2,
        }
        assert out["visibility"] == {"hidden": 1, "visible": 3, "not_recorded": 3}
        assert out["recorded_rows"] == 6  # r5 两键都缺席
        assert out["other_values"] == {"weird": 1, "int": 1}

    def test_string_visibility_is_not_recorded_not_visible(self):
        """`"false"` 既不是 True 也不是 False：记未记录，不折成可见。"""
        out = oracle_provenance_stats(
            [{"task_id": "t1", "oracle_type": "generated_test", "test_visible_to_system": "false"}]
        )
        assert out["visibility"] == {"not_recorded": 1}

    def test_empty_repo_verification_is_not_a_repo_row(self):
        """`repo_verification` 为空 dict 的行没做过仓库级验收，不得进 repo 行/违规。"""
        out = oracle_provenance_stats(
            [
                {
                    "task_id": "t1",
                    "repo_verification": {},
                    "oracle_type": "generated_test",
                    "test_visible_to_system": True,
                }
            ]
        )
        assert out["repo_rows"] == 0
        assert out["n_violations"] == 0

    def test_repo_row_with_gold_but_visible_is_a_violation(self):
        """只查 oracle_type 不查可见性会放过「gold 但对系统可见」这一半错标。"""
        out = oracle_provenance_stats(
            [
                {
                    "task_id": "t1",
                    "repo_verification": {"passed": True},
                    "oracle_type": ORACLE_TYPE_REPO_GOLD,
                    "test_visible_to_system": True,
                }
            ]
        )
        assert out["repo_rows"] == 1
        assert out["n_violations"] == 1
        assert out["violations"] == ["t1"]

    def test_violation_detail_is_capped_but_the_count_is_not(self):
        rows = [
            {
                "task_id": f"t{i}",
                "repo_verification": {"passed": True},
                "oracle_type": "generated_test",
                "test_visible_to_system": True,
            }
            for i in range(21)
        ]
        out = oracle_provenance_stats(rows)
        assert out["n_violations"] == 21
        assert len(out["violations"]) == 20

    def test_missing_arm_rows_return_zero_counts(self):
        """臂存在但没有行数据（值为 None）：给零计数，不是"没有这个臂"。"""
        out = oracle_provenance_summary({"plain_llm": None})["plain_llm"]
        assert out["n_rows"] == 0
        assert out["by_type"] == {}
        assert out["consistent"] is True

    def test_helper_itself_tolerates_none_rows(self):
        """助手自身的 `rows or []` 必须有独立输入能命名它（直接喂 None）。

        臂级包装器也写了一遍兜底，两者对 `{"arm": None}` 互为冗余：只删包装器
        那半永远 0 红，因此本锁钉的是助手侧，包装器侧不设锚点（AB-14 判据）。
        """
        out = oracle_provenance_stats(None)
        assert out["n_rows"] == 0
        assert out["repo_rows"] == 0
        assert out["consistent"] is True


class TestConstructionPointWiring:
    """BT 的落点之二：五个构造点必须真的把描述符传进结果行。

    只改 `_oracle_descriptor` 不算修好——`run_single_task` 里任何一处漏传
    `oracle=`，那一支的行就退回历史口径（生成测试 + 可见）。
    """

    def _calls(self) -> list[ast.Call]:
        src = (ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        runner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_single_task")
        return [
            n for n in ast.walk(runner) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_build_task_result"
        ]

    def test_all_five_construction_points_pass_the_descriptor(self):
        calls = self._calls()
        assert len(calls) == 5
        for call in calls:
            assert any(kw.arg == "oracle" for kw in call.keywords), ast.unparse(call)[:80]

    def test_success_points_pass_state_and_failure_points_pass_none(self):
        src = (ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8")
        assert src.count("oracle=_oracle_descriptor(task, baseline, final_state)") == 2
        assert src.count("oracle=_oracle_descriptor(task, baseline, None)") == 3

    @staticmethod
    def _term(expr: ast.expr) -> str:
        """归一化一个条件项：脱掉 `bool(...)`、`task.metadata` 写作 `metadata`、引号统一。"""
        text = ast.unparse(expr).replace('"', "'")
        while text.startswith("bool(") and text.endswith(")"):
            text = text[5:-1]
        return text.replace("task.metadata", "metadata")

    def test_descriptor_condition_equals_the_real_routing_condition(self):
        """检查点声明的条件必须与真实仓库级验收路由**同式**（结构比对，不是文本猜测）。

        路由若新增第七个条件而描述符没跟上，声明就又变成"按状态猜"——本锁把两者
        的条件项集合作为结构等式钉住。
        """
        tree = ast.parse((ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8"))

        def _and_terms(func_name: str) -> set[str]:
            """取某个函数里唯一那个"带 source 判定"的 And 条件项集合。"""
            fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name)
            hits = [
                node
                for node in ast.walk(fn)
                if isinstance(node, ast.BoolOp)
                and isinstance(node.op, ast.And)
                and any(self._term(v).startswith("metadata.get('source')") for v in node.values)
            ]
            assert len(hits) == 1, (func_name, [h.lineno for h in hits])
            return {self._term(t) for t in hits[0].values}

        descriptor = _and_terms("_oracle_descriptor")
        assert len(descriptor) == 6, descriptor

        def _writes_repo_verification(node: ast.AST) -> bool:
            return any(
                isinstance(sub, ast.Assign)
                and any(
                    isinstance(t, ast.Subscript)
                    and getattr(t.value, "id", "") == "final_state"
                    and getattr(t.slice, "value", None) == "repo_verification"
                    for t in sub.targets
                )
                for sub in ast.walk(node)
            )

        routing = [
            node.test
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp) and _writes_repo_verification(node)
        ]
        assert len(routing) == 1, routing

        assert descriptor == {self._term(t) for t in routing[0].values}
        assert len(routing[0].values) == 6


class TestReportSurface:
    """BT 的落点：两个键必须真的出现在报告里（改前全仓零读端）。"""

    def test_build_analysis_and_render_flag_violation(self):
        from experiments.analyze_results import build_analysis, render_markdown

        data = {
            "results": {
                "aitester": {
                    "details": [
                        {
                            "task_id": "t1",
                            "passed": True,
                            "detection_rate": 1,
                            "repo_verification": {"passed": True},
                            # 修复前形态：repo 验收却标生成测试 + 可见
                            "oracle_type": "generated_test",
                            "test_visible_to_system": True,
                        }
                    ]
                }
            }
        }
        analysis = build_analysis(data)
        assert analysis["per_baseline"]["aitester"]["oracle_provenance"]["n_violations"] == 1

        md = render_markdown(analysis, "x.json")
        assert "## 验收 oracle 来源与可见性" in md
        assert "repo 行必须 gold + 不可见" in md
        assert "t1" in md

    @staticmethod
    def _md(rows: list[dict]) -> str:
        from experiments.analyze_results import build_analysis, render_markdown

        analysis = build_analysis({"results": {"aitester": {"details": rows}}})
        return render_markdown(analysis, "x.json")

    def test_section_absent_when_no_row_recorded_the_checkpoint(self):
        """一行都没有（臂为空）时节整段消失：不能渲染一张全零表读成「都记了」。"""
        assert "## 验收 oracle 来源与可见性" not in self._md([])

    def test_table_cells_show_repo_and_violation_counts(self):
        """三档 repo 行各出一例：`repo 缺声明` 格必须由**非零**值钉住。

        只放一致 + 违规两行时该格真为 0，把渲染改成常量 `0` 是恒等操作、拦不住
        （T44 首轮因此存活）。
        """
        md = self._md(
            [
                {
                    "task_id": "t1",
                    "repo_verification": {"passed": True},
                    "oracle_type": ORACLE_TYPE_REPO_GOLD,
                    "test_visible_to_system": False,
                },
                {
                    "task_id": "t2",
                    "repo_verification": {"passed": True},
                    "oracle_type": "generated_test",
                    "test_visible_to_system": True,
                },
                {"task_id": "t3", "repo_verification": {"passed": False}},
            ]
        )
        assert "| aitester | 1 | 0 | 1 | 1 | 0 | 3 | 3 | 1 | 1 | 1 |" in md

    def test_clean_arm_prints_no_violation_line(self):
        md = self._md(
            [
                {
                    "task_id": "t1",
                    "repo_verification": {"passed": True},
                    "oracle_type": ORACLE_TYPE_REPO_GOLD,
                    "test_visible_to_system": False,
                }
            ]
        )
        assert "**不一致（repo 行必须 gold + 不可见）**" not in md
        assert "词表外取值（单列，不并入任何档）" not in md

    def test_out_of_vocabulary_value_is_named_in_the_report(self):
        md = self._md([{"task_id": "t1", "oracle_type": "human_adjudicated", "test_visible_to_system": True}])
        assert "词表外取值（单列，不并入任何档）" in md
        assert "human_adjudicated" in md

    def test_footnote_keeps_both_reading_calibers(self):
        """脚注是本节唯一的口径声明：未记录 ≠ 生成测试验收、repo 行的双条件。"""
        md = self._md([{"task_id": "t1", "passed": True}])
        assert "`未记录` = 该行没有这两个键" in md
        assert "**不等于**「生成测试验收」" in md
        assert "必须同时满足 `gold_fail_to_pass` 与 `False`" in md

    def test_footnote_keeps_the_missing_declaration_caliber(self):
        """缺声明那一列必须自带口径：不记作错标，只缺一键才算不完整。"""
        md = self._md([{"task_id": "t1", "passed": True, "repo_verification": {"passed": False}}])
        assert "`repo 缺声明` = 有仓库级验收但**两个键都未记录**" in md
        assert "**不计入不一致**" in md
        assert "只记录了一个键属不完整声明，仍计入不一致" in md
        assert "**不一致（repo 行必须 gold + 不可见）**" not in md

    def test_archive_repo_rows_are_unrecorded_not_mislabelled(self):
        """真归档实钉：6 份 g8 批次共 50 条 repo 行，两键全缺 → 50 缺声明、0 不一致。

        本轮第一版读端把这 50 行折成了「不一致」，与手册 §3 的声明相反（见评审
        手册 §6 自纠）；本锁让"缺键 ≠ 错标"成为可重跑断言，而不是一句叙述。
        """
        paths = sorted(p for p in (ROOT / "experiments" / "results").rglob("*.json") if "g8_" in str(p.parent))
        # B1 批（2026-10-30）口径收紧：历史 6 份 g8 批次已随 2026-10-24 清除退场；
        # 今天新增的 g8_fullstack_20261030 复测目录会被 "g8_" 前缀误命中，但其
        # 任务全部被 M3 门禁剔除（repo_rows=0）——前提（存在含 repo_rows 的
        # g8 批次工件）不成立时显式 skip，不把"没有可断言对象"折成断言失败。
        import json as _json

        has_repo_rows = False
        for _p in paths:
            try:
                _pl = _json.loads(_p.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError, UnicodeDecodeError):
                continue
            for _blk in (_pl.get("results") or {}).values():
                _det = _blk.get("details") if isinstance(_blk, dict) else None
                if isinstance(_det, list) and any(isinstance(r, dict) and r.get("repo_rows") for r in _det):
                    has_repo_rows = True
                    break
            if has_repo_rows:
                break
        if not paths or not has_repo_rows:
            pytest.skip(
                "含 repo_rows 的 g8 批次工件不在本地（历史批次已随 2026-10-24 清除退场；"
                "新 g8 复测目录任务全被 M3 剔除）——实钉前提不成立，显式跳过"
            )
        import json

        repo_rows = unrecorded = violations = consistent = arms = 0
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError, UnicodeDecodeError):
                continue
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, dict):
                continue
            for arm, block in results.items():
                details = block.get("details") if isinstance(block, dict) else None
                if not isinstance(details, list) or not all(isinstance(r, dict) for r in details):
                    continue
                out = oracle_provenance_stats(details)
                if not out["repo_rows"]:
                    continue
                arms += 1
                repo_rows += out["repo_rows"]
                unrecorded += out["repo_rows_unrecorded"]
                consistent += out["repo_rows_consistent"]
                violations += out["n_violations"]
                assert (
                    out["repo_rows_unrecorded"] + out["repo_rows_consistent"] + out["n_violations"] == out["repo_rows"]
                ), (path, arm)

        assert arms == 6, arms
        assert (repo_rows, unrecorded, consistent, violations) == (50, 50, 0, 0)
