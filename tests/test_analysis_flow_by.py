"""BY 轮（2026-10-23）：分析集流量账的读侧锁。

缺陷形态（零 LLM；普查工具 `scripts/tools/by_analysis_flow_census.py`）：

- 报告 `## 数据来源` 只列**纳入**的 110 份批次，此前四层文件级剔除
  （数据集白名单 77 份 / 886 行、schema 不完备 59 份 / 2,463 行、读取/加载
  失败、未登记基线 300 行）与两层行级折叠（重复 task_id 6,449 行、字段
  None 45/52）一层也不显示；
- 读者看到“110 份 / n=187”无法核对 10,659 行里哪些行被哪条规则挡在门外，
  也无法知道 7,010 行里 6,449 行被去重折叠——PRISMA 2020 流程图要求逐阶段
  数量与排除理由且与正文对账；Hurlbert（1984）伪重复要求 n 只数独立观测
  单元，折叠量必须披露。

修复口径：**纯读侧**。`src/` 零改动；新增 `experiments/_analysis_flow.py`
（单一事实源）+ `statistical_analysis.analysis_flow_stats` + 控制台一行 +
`## 数据来源` 子章节。加载器 `_load_batch_file` 的判定顺序、判定值与方向
一处不动。

锁的形状（沿用 BW/BX 纪律）：全归档读数（246 / 10,659 → 77 / 886 →
59 / 2,463 → 110 / 7,310 → 7,010 → 6,449 → 561 …）是**实测读数**，登记在
手册并附复现命令，不在这里锁死（新批次一旦落盘就会漂移）。本文件锁的是：
①归层顺序与加载器一致、②文件级剔除分账与对账闭合、③白名单/混批口径、
④行级去重“最新批次优先且不看字段值”、⑤None 在去重后剔除、⑥报告面逐格
与脚注、⑦控制台摘要、⑧五份具名冻结批次的逐层读数。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import experiments._analysis_flow as af
import experiments.statistical_analysis as sa
from experiments.statistical_analysis import analysis_flow_stats, run_all_statistics

ROOT = Path(__file__).resolve().parents[1]
TRACKED = frozenset(sa._BASELINES)
SUPPORTED = frozenset(sa._SUPPORTED_DATASETS)
UNTRACKED = "plain_llm_df_spec"

#: 具名冻结批次：逐层读数由 `scripts/tools/by_analysis_flow_census.py --segment c` 复核。
#: 五份覆盖五种形态：现代三臂 261 行 / 两臂 100 行且含字段 None / schema 不完备
#: 冒烟批次 / 数据集白名单外 / 全部行属于未登记基线。
PINNED_BATCHES: dict[str, dict[str, Any]] = {
    "experiments/results/t_round_b2_main_batch_20261018/seed42/benchmark_synthetic_20261018_100552.json": {
        "layer": "included",
        "info": {},
        "rows": 261,
        "per_baseline": {"aitester": 87, "plain_llm": 87, "plain_llm_df": 87},
        "tracked_rows": 261,
        "untracked": {},
        "unique": {"aitester": 87, "plain_llm": 87, "plain_llm_df": 87},
        "none": {
            "aitester": {"passed": 0, "detection_rate": 0, "repair_rate": 0},
            "plain_llm": {"passed": 0, "detection_rate": 0, "repair_rate": 0},
            "plain_llm_df": {"passed": 0, "detection_rate": 0, "repair_rate": 0},
        },
    },
    "experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json": {
        "layer": "included",
        "info": {},
        "rows": 100,
        "per_baseline": {"plain_llm": 50, "plain_llm_df": 50},
        "tracked_rows": 100,
        "untracked": {},
        "unique": {"plain_llm": 50, "plain_llm_df": 50},
        "none": {
            "plain_llm": {"passed": 0, "detection_rate": 14, "repair_rate": 9},
            "plain_llm_df": {"passed": 0, "detection_rate": 14, "repair_rate": 9},
        },
    },
    "experiments/results/main_batch/benchmark_synthetic_20261001_112528.json": {
        "layer": "schema_incomplete",
        "info": {},
        "rows": 10,
        "per_baseline": {"aitester": 5, "plain_llm": 5},
        "tracked_rows": 10,
        "untracked": {},
    },
    "experiments/results/benchmark_examples_20260813_125502.json": {
        "layer": "unsupported_dataset",
        "info": {"dataset": "examples"},
        "rows": 3,
        "per_baseline": {"aitester": 1, "plain_llm": 1, "single_agent": 1},
        "tracked_rows": 3,
        "untracked": {},
    },
    "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json": {
        "layer": "included",
        "info": {},
        "rows": 50,
        "per_baseline": {"plain_llm_df_spec": 50},
        "tracked_rows": 0,
        "untracked": {"plain_llm_df_spec": 50},
        "unique": {},
        "none": {},
    },
}


def _row(
    task_id: str | None,
    *,
    passed: bool = True,
    detection_rate: float | None = 1.0,
    repair_rate: float | None = 1.0,
) -> dict[str, Any]:
    row: dict[str, Any] = {"passed": passed, "detection_rate": detection_rate, "repair_rate": repair_rate}
    if task_id is not None:
        row["task_id"] = task_id
    return row


def _write_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def _build_tree(root: Path) -> dict[str, str]:
    """五份 benchmark 文件 + 一份扫描面外文件；覆盖每一层与一种失败。"""
    names = {
        "included": "benchmark_a_20260101_000000.json",
        "schema": "benchmark_b_20260101_000001.json",
        "unsupported": "benchmark_c_20260101_000002.json",
        "read_error": "benchmark_d_20260101_000003.json",
        "load_error": "benchmark_e_20260101_000004.json",
        "outside": "other_20260101_000005.json",
    }
    _write_json(
        root / names["included"],
        {
            "dataset": "synthetic",
            "results": {
                "aitester": {"details": [_row("t1"), _row("t2", detection_rate=None)]},
                UNTRACKED: {"details": [_row("x1")]},
            },
        },
    )
    _write_json(
        root / names["schema"],
        {
            "dataset": "synthetic",
            "results": {"aitester": {"details": [_row("t9", detection_rate=None, repair_rate=None)]}},
        },
    )
    _write_json(
        root / names["unsupported"],
        {
            "dataset": "examples",
            "results": {"aitester": {"details": [_row("e1")]}, "plain_llm": {"details": [_row("e2")]}},
        },
    )
    (root / names["read_error"]).write_text("{not json", encoding="utf-8")
    _write_json(
        root / names["load_error"],
        {
            "dataset": "synthetic",
            "results": {
                "aitester": {"details": [_row("t5")]},
                "plain_llm": {"details": "oops"},
            },
        },
    )
    _write_json(root / names["outside"], {"dataset": "synthetic", "results": {"aitester": {"details": [_row("o1")]}}})
    return names


def _build_dedup_tree(root: Path) -> None:
    """新批次在前：t1 最新行的 repair_rate=None，旧批次有可测值——不得顶替。"""
    _write_json(
        root / "benchmark_new_20260102_000000.json",
        {"dataset": "synthetic", "results": {"aitester": {"details": [_row("t1", repair_rate=None)]}}},
    )
    _write_json(
        root / "benchmark_old_20260101_000000.json",
        {
            "dataset": "synthetic",
            "results": {
                "aitester": {
                    "details": [
                        _row("t1", passed=False, detection_rate=0.0, repair_rate=1.0),
                        _row("t2", passed=False, detection_rate=0.0, repair_rate=1.0),
                        _row(None),
                    ]
                }
            },
        },
    )


def _classify(doc: Any, *, allow_schema_mixed: bool = False) -> tuple[str, dict[str, str]]:
    return af.classify_document(
        doc,
        supported_datasets=SUPPORTED,
        tracked_baselines=TRACKED,
        allow_schema_mixed=allow_schema_mixed,
    )


class TestClassifyOrder:
    """归层顺序必须与 `_load_batch_file` 一致，否则流量账与实际纳入对不上。"""

    def test_dataset_whitelist_runs_before_schema_and_shape(self) -> None:
        # 数据集外 + results 形状非法：加载器先看数据集，故不是 load_error
        assert _classify({"dataset": "examples", "results": []})[0] == "unsupported_dataset"
        # synthetic + 结构合法但 schema 全 None：默认口径在形状校验之前剔除
        empty = {"dataset": "synthetic", "results": {"aitester": {"details": []}}}
        assert _classify(empty)[0] == "schema_incomplete"
        assert _classify(empty, allow_schema_mixed=True)[0] == "included"
        # results 不是字典时 schema 检查自身抛错——加载器同样整份失败（不是 schema 剔除）
        assert _classify({"dataset": "synthetic", "results": []})[0] == "load_error"
        assert _classify({"dataset": "synthetic", "results": []}, allow_schema_mixed=True)[0] == "load_error"

    def test_unhashable_dataset_is_load_error_like_loader(self) -> None:
        # 加载器 data.get("dataset") 后做集合成员判定，list 会抛 TypeError → 整份失败
        assert _classify({"dataset": ["synthetic"], "results": {}})[0] == "load_error"
        assert _classify(["not", "a", "dict"])[0] == "load_error"

    def test_tracked_block_shape_errors_are_load_error(self) -> None:
        schema_ok = {"aitester": {"details": [_row("t1")]}}
        assert _classify({"dataset": "synthetic", "results": schema_ok})[0] == "included"
        assert _classify({"dataset": "synthetic", "results": {**schema_ok, "plain_llm": None}})[0] == "load_error"
        assert (
            _classify({"dataset": "synthetic", "results": {**schema_ok, "plain_llm": {"details": "x"}}})[0]
            == "load_error"
        )
        assert (
            _classify({"dataset": "synthetic", "results": {**schema_ok, "plain_llm": {"details": ["x"]}}})[0]
            == "load_error"
        )

    def test_untracked_block_shape_is_ignored_like_loader(self) -> None:
        doc = {"dataset": "synthetic", "results": {"aitester": {"details": [_row("t1")]}, UNTRACKED: "oops"}}
        assert _classify(doc) == ("included", {})

    def test_missing_dataset_label_is_reported_explicitly(self) -> None:
        layer, info = _classify({"results": {}})
        assert layer == "unsupported_dataset"
        assert info == {"dataset": "<缺失>"}


class TestSchemaAndRowCounts:
    def test_schema_completeness_requires_a_non_none_detection_rate(self) -> None:
        assert af.batch_is_m1_schema_complete({"results": {}}) is False
        assert (
            af.batch_is_m1_schema_complete({"results": {"aitester": {"details": [{"detection_rate": None}]}}}) is False
        )
        # 0.0 是「测到了且检出率为 0」，不是缺失
        assert af.batch_is_m1_schema_complete({"results": {"aitester": {"details": [{"detection_rate": 0}]}}}) is True
        assert af.batch_is_m1_schema_complete({"results": {"aitester": {"details": ["x"]}}}) is False
        assert af.batch_is_m1_schema_complete({"results": {"aitester": None}}) is False

    def test_row_counts_only_counts_dict_rows_in_list_details(self) -> None:
        doc = {
            "results": {
                "a": {"details": [{"x": 1}, "bad", None]},
                "b": {"details": "no"},
                "c": "no",
            }
        }
        assert af._row_counts(doc) == (1, {"a": 1})
        assert af._row_counts(None) == (0, {})

    def test_field_and_layer_constants_are_closed(self) -> None:
        assert af.BATCH_GLOB == "benchmark_*.json"
        assert af.FLOW_FIELDS == ("passed", "detection_rate", "repair_rate")
        assert set(af.LAYER_ORDER) == {
            "included",
            "unsupported_dataset",
            "schema_incomplete",
            "read_error",
            "load_error",
        }


class TestFileLevelFlow:
    def test_glob_flow_accounts_every_layer_and_reconciles(self, tmp_path: Path) -> None:
        names = _build_tree(tmp_path)
        flow = af.flow_stats(
            tmp_path,
            supported_datasets=SUPPORTED,
            tracked_baselines=TRACKED,
        )
        assert flow["mode"] == "glob"
        assert flow["scan"] == {"files": 5, "rows": 7}
        assert flow["status"] == {
            "included": {"files": 1, "rows": 3},
            "unsupported_dataset": {"files": 1, "rows": 2},
            "schema_incomplete": {"files": 1, "rows": 1},
            "read_error": {"files": 1, "rows": 0},
            "load_error": {"files": 1, "rows": 1},
        }
        assert flow["datasets"] == {"examples": 1}
        assert flow["untracked_baselines"] == {UNTRACKED: 1}
        assert flow["included"] == {"files": 1, "rows_all": 3, "rows_tracked": 2}
        assert flow["read_errors"] == [{"file": names["read_error"], "error": "JSONDecodeError"}]
        assert flow["whitelist"] is None

    def test_glob_ignores_non_benchmark_files_but_archive_universe_counts_them(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        archive = af.archive_universe(tmp_path)
        assert archive == {"files": 5, "rows": 8, "non_benchmark_files": 1, "non_benchmark_rows": 1}

    def test_whitelist_dedups_paths_and_reports_missing_file(self, tmp_path: Path) -> None:
        names = _build_tree(tmp_path)
        flow = af.flow_stats(
            tmp_path,
            supported_datasets=SUPPORTED,
            tracked_baselines=TRACKED,
            batch_files=[names["included"], names["included"], "benchmark_missing.json"],
        )
        assert flow["mode"] == "whitelist"
        assert flow["scan"] == {"files": 2, "rows": 3}
        assert flow["included"] == {"files": 1, "rows_all": 3, "rows_tracked": 2}
        assert flow["read_errors"] == [{"file": "benchmark_missing.json", "error": "FileNotFoundError"}]
        assert flow["status"]["unsupported_dataset"] == {"files": 0, "rows": 0}
        assert flow["whitelist"] == [str(tmp_path / names["included"]), str(tmp_path / "benchmark_missing.json")]

    def test_allow_schema_mixed_includes_layer_and_records_default_count(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        flow = af.flow_stats(
            tmp_path,
            supported_datasets=SUPPORTED,
            tracked_baselines=TRACKED,
            allow_schema_mixed=True,
        )
        assert flow["status"]["schema_incomplete"] == {"files": 0, "rows": 0}
        assert flow["included"]["files"] == 2
        assert flow["included"]["rows_all"] == 4
        assert flow["included"]["rows_tracked"] == 3
        assert flow["schema_incomplete_if_default"] == {"files": 1, "rows": 1}


class TestRowLevelFlow:
    def test_latest_row_occupies_even_when_field_is_none(self, tmp_path: Path) -> None:
        _build_dedup_tree(tmp_path)
        results, sources = sa.load_experiment_results_with_sources(str(tmp_path))
        assert sources == ["benchmark_new_20260102_000000.json", "benchmark_old_20260101_000000.json"]
        flow = af.loaded_flow(results)
        assert flow["rows"] == 4
        assert flow["unique"] == 2
        assert flow["duplicates"] == 1
        assert flow["no_task_id"] == 1
        assert flow["fields"]["repair_rate"] == {"none": 1, "measurable": 1}
        assert flow["per_baseline"]["aitester"]["rows"] == 4
        assert flow["per_baseline"]["aitester"]["unique"] == 2
        assert flow["per_baseline"]["aitester"]["fields"]["repair_rate"] == {"none": 1, "measurable": 1}
        assert flow["per_baseline"]["aitester"]["fields"]["detection_rate"] == {"none": 0, "measurable": 2}

    def test_loaded_flow_is_empty_safe(self) -> None:
        flow = af.loaded_flow({})
        assert flow["rows"] == 0
        assert flow["unique"] == 0
        assert flow["fields"] == {field: {"none": 0, "measurable": 0} for field in af.FLOW_FIELDS}

    def test_analysis_flow_stats_closes_both_reconciliations(self, tmp_path: Path) -> None:
        names = _build_tree(tmp_path)
        data, sources = sa.load_experiment_results_with_sources(str(tmp_path))
        flow = analysis_flow_stats(data, str(tmp_path))
        assert flow["included"]["files"] == len(sources) == 1
        assert flow["included"]["rows_tracked"] == sum(len(v) for v in data.values()) == 2
        assert flow["loaded"]["rows"] == 2
        assert flow["loaded"]["unique"] == 2
        assert flow["reconciles"] is True
        assert flow["archive"] == {"files": 5, "rows": 8, "non_benchmark_files": 1, "non_benchmark_rows": 1}
        # 白名单口径不扫全归档（扫描面就是清单本身）
        white = analysis_flow_stats(data, str(tmp_path), batch_files=[names["included"]])
        assert white["mode"] == "whitelist"
        assert white["archive"] is None

    def test_file_level_reconciliation_clause_is_live(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """文件层对账单独可失效：扫描−剔除 ≠ 载入时不得仍报"闭合"。"""
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path))
        original = af.flow_stats

        def doctored(*args: Any, **kwargs: Any) -> dict[str, Any]:
            flow = original(*args, **kwargs)
            flow["included"]["rows_all"] += 1
            return flow

        monkeypatch.setattr(af, "flow_stats", doctored)
        flow = analysis_flow_stats(data, str(tmp_path))
        assert flow["reconciles"] is False

    def test_unclosed_reconciliation_is_reported_not_hidden(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path))
        flow = analysis_flow_stats(data, str(tmp_path))
        assert flow["reconciles"] is True
        # 人为让载入行多于文件账（模拟加载器多写了一行）：对账必须转 False
        data["aitester"].append(_row("t_extra"))
        tampered = analysis_flow_stats(data, str(tmp_path))
        assert tampered["loaded"]["rows"] == 3
        assert tampered["reconciles"] is False
        text = "\n".join(af.render_analysis_flow_lines(tampered))
        assert "**对账未闭合，见下方差异。**" in text


class TestRenderingAndConsole:
    def test_section_table_footnotes_and_reconciliation(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path))
        flow = analysis_flow_stats(data, str(tmp_path))
        lines = af.render_analysis_flow_lines(flow)
        text = "\n".join(lines)
        assert "### 分析集流量（BY：逐层剔除与去重）" in text
        assert "| 扫描（glob `benchmark_*.json`） | 5 | 7 | 加载器唯一扫描面 |" in text
        assert "| 数据集白名单外 | −1 | −2 | examples 1 |" in text
        assert "| schema 不完备（默认剔除） | −1 | −1 |" in text
        assert f"| 基线未登记 | 0 | −1 | {UNTRACKED} 1 |" in text
        assert "| **载入** | **1** | **2** |" in text
        assert "| 重复 task_id 折叠 | — | −0 |" in text
        assert "| **唯一 task 行** | — | **2** |" in text
        assert "| `detection_rate`：None / 可测 | — | 1 / 1 |" in text
        assert "**None ≠ 0**" in text
        assert "= **2**（载入 2）" in text
        assert "两项均闭合。" in text
        assert "**5 份 / 8 行**" in text and "**1 份 / 1 行**" in text
        assert "混批口径（`--allow-schema-mixed`）" in text and "**1 份 / 1 行**" in text
        assert "PRISMA 2020" in text and "Hurlbert（1984）" in text
        assert "只记账" in text

    def test_mixed_mode_footnote_reports_default_would_be_layer(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path), allow_schema_mixed=True)
        flow = analysis_flow_stats(data, str(tmp_path), allow_schema_mixed=True)
        text = "\n".join(af.render_analysis_flow_lines(flow))
        assert "| schema 不完备（默认剔除） | −0 | −0 |" in text
        assert "本报告以 `--allow-schema-mixed` 口径运行" in text
        assert "**1 份 / 1 行**" in text
        assert "默认口径会剔除的" in text
        assert "两个口径的读数不可混用" in text
        assert "混批口径（`--allow-schema-mixed`）会把 schema 层" not in text

    def test_unclosed_marker_is_written(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path))
        flow = analysis_flow_stats(data, str(tmp_path))
        flow["reconciles"] = False
        text = "\n".join(af.render_analysis_flow_lines(flow))
        assert "**对账未闭合，见下方差异。**" in text
        assert "两项均闭合。" not in text

    def test_console_line_names_every_exclusion(self, tmp_path: Path) -> None:
        _build_tree(tmp_path)
        data, _ = sa.load_experiment_results_with_sources(str(tmp_path))
        line = af.flow_console_line(analysis_flow_stats(data, str(tmp_path)))
        assert "扫描 5 份 / 7 行" in line
        assert "数据集外 2 行" in line and "schema 1 行" in line
        assert "读取/加载失败 1 行" in line and "未登记基线 1 行" in line
        assert "载入 1 份 / 2 行" in line
        assert "折叠重复 0 行" in line and "唯一 2 行" in line
        assert "detection_rate None 1" in line

    def test_report_data_source_section_and_console_are_wired(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_json(
            tmp_path / "benchmark_report_20260101_000000.json",
            {
                "dataset": "synthetic",
                "results": {
                    "aitester": {"details": [_row(f"t{i}", passed=True) for i in range(3)]},
                    "plain_llm": {"details": [_row(f"t{i}", passed=False, detection_rate=0.0) for i in range(3)]},
                },
            },
        )
        report = tmp_path / "report.md"
        run_all_statistics(str(tmp_path), str(report))
        text = report.read_text(encoding="utf-8")
        assert "## 数据来源" in text
        assert "### 分析集流量（BY：逐层剔除与去重）" in text
        assert "| **载入** | **1** | **6** |" in text
        assert "| **唯一 task 行** | — | **6** |" in text
        assert "两项均闭合。" in text
        out = capsys.readouterr().out
        assert "分析集流量（BY）：扫描 1 份 / 6 行" in out
        assert "折叠重复 0 行 → 唯一 6 行" in out


class TestPinnedBatches:
    @pytest.mark.parametrize("rel", sorted(PINNED_BATCHES))
    def test_layer_rows_and_row_accounting(self, rel: str, capsys: pytest.CaptureFixture[str]) -> None:
        expected = PINNED_BATCHES[rel]
        doc = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        layer, info = _classify(doc)
        assert layer == expected["layer"]
        assert info == expected["info"]

        rows, per_baseline = af._row_counts(doc)
        assert rows == expected["rows"]
        assert per_baseline == expected["per_baseline"]
        assert sum(v for b, v in per_baseline.items() if b in TRACKED) == expected["tracked_rows"]
        assert {b: v for b, v in per_baseline.items() if b not in TRACKED} == expected["untracked"]

        loaded: dict[str, list[dict[str, Any]]] = {baseline: [] for baseline in sa._BASELINES}
        accepted = sa._load_batch_file(loaded, ROOT / rel)
        capsys.readouterr()
        assert accepted is (expected["layer"] == "included")
        flow = af.loaded_flow(loaded)
        if not accepted:
            assert flow["rows"] == 0
            assert flow["unique"] == 0
            return
        assert flow["rows"] == expected["tracked_rows"]
        assert {b: v["unique"] for b, v in flow["per_baseline"].items() if v["rows"]} == expected["unique"]
        assert {
            b: {f: v["fields"][f]["none"] for f in af.FLOW_FIELDS} for b, v in flow["per_baseline"].items() if v["rows"]
        } == expected["none"]
