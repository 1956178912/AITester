"""EL 轮：P2P 门禁判无效的行不得在终局失效分布里冒充「运行异常/限流」。

缺陷族：批次汇总承诺 harness_invalid（基线 P2P 不达标）实例「从统计中剔除」
（summary 同时给出 harness_invalid_count / effective_total / 有效通过率），
但 `_aggregate_failure_buckets` 只看 `failure_bucket` 是否为空：门禁早退行
（未进入工作流）与真崩溃/限流行同形计入 `unclassified_rows`，报告层还把
它们标注为「无工作流终局状态〔运行异常/限流〕」——同一批工件里「剔除」与
「计入」并存，且原因被写成事实错误的那一个。

修法口径：
1. 聚合器把 harness_invalid 行单列 `harness_invalid_rows`，不参与桶分类；
2. 恒等式 total + unclassified_rows + harness_invalid_rows == total_rows；
3. 报告层两因分开披露，各自说清原因（不合并成「运行异常/限流」一句）；
4. 逐行四键口径不变：门禁行仍 None（没有终局状态可分类，不臆造桶）。
"""

import experiments.run_benchmark as rb
from experiments.run_benchmark import _aggregate_failure_buckets, _build_task_result
from src.datasets.dataset_loader import BenchmarkTask
from src.observability.failure_taxonomy import render_markdown, summarize_batch


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="repo__repo-1",
        repo_name="repo/repo",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "test"},
    )


def _gate_row() -> dict:
    return _build_task_result(
        _make_task(),
        0.0,
        diagnosis="M3 P2P 门禁：harness_invalid（p2p_low）",
        error_category="harness_invalid",
        harness_invalid=True,
    )


def _crash_row() -> dict:
    return _build_task_result(_make_task(), 0.1, diagnosis="执行异常: boom", error_category="error")


def _success_row() -> dict:
    return _build_task_result(_make_task(), 0.2, final_state={"test_passed": True})


class TestAggregation:
    def test_gate_rows_are_not_filed_as_runtime_crashes(self) -> None:
        summary = _aggregate_failure_buckets([_success_row(), _gate_row(), _crash_row()])

        assert summary["harness_invalid_rows"] == 1
        assert summary["unclassified_rows"] == 1, "只有真崩溃行才是「无终局状态」"
        assert summary["total"] == 1
        assert summary["total_rows"] == 3
        assert summary["counts"]["task_completed"] == 1
        assert summary["shares"]["task_completed"] == 1.0

    def test_all_gate_batch_has_zero_runtime_unclassified(self) -> None:
        summary = _aggregate_failure_buckets([_gate_row(), _gate_row()])

        assert summary["harness_invalid_rows"] == 2
        assert summary["unclassified_rows"] == 0
        assert summary["total"] == 0
        assert summary["total_rows"] == 2
        assert all(v == 0.0 for v in summary["shares"].values())

    def test_identity_holds_for_every_row(self) -> None:
        for rows in ([], [_gate_row()], [_success_row(), _gate_row(), _crash_row()]):
            summary = _aggregate_failure_buckets(rows)
            assert (
                summary["total"] + summary["unclassified_rows"] + summary["harness_invalid_rows"]
                == summary["total_rows"]
            ), rows

    def test_batch_without_gate_rows_is_unchanged(self) -> None:
        summary = _aggregate_failure_buckets([_success_row(), _crash_row()])

        assert summary["harness_invalid_rows"] == 0
        assert summary["unclassified_rows"] == 1
        assert summary["total"] == 1
        assert "harness 前置门禁" not in render_markdown(summary)
        assert "另有 1 个任务无工作流终局状态" in render_markdown(summary)

    def test_empty_batch_reports_zero_gate_rows(self) -> None:
        summary = _aggregate_failure_buckets([])

        assert summary["harness_invalid_rows"] == 0
        assert summary["unclassified_rows"] == 0
        assert "无工作流终局状态" not in render_markdown(summary)


class TestRenderMarkdown:
    def test_gate_only_batch_discloses_gate_exclusion(self) -> None:
        markdown = render_markdown(_aggregate_failure_buckets([_gate_row(), _gate_row()]))

        assert "另有 2 个任务因 harness 前置门禁未执行〔基线 P2P 不达标〕" in markdown
        assert "无工作流终局状态" not in markdown, "门禁行不是崩溃行，措辞不得冒充"
        assert "批次共 2 行" in markdown

    def test_mixed_exclusions_are_disclosed_separately(self) -> None:
        markdown = render_markdown(_aggregate_failure_buckets([_gate_row(), _crash_row()]))

        assert "1 个任务无工作流终局状态〔运行异常/限流〕" in markdown
        assert "1 个任务因 harness 前置门禁未执行〔基线 P2P 不达标〕" in markdown
        assert "批次共 2 行" in markdown

    def test_summarize_batch_output_stays_backward_compatible(self) -> None:
        markdown = render_markdown(summarize_batch([{"test_passed": True}]))

        assert "总计：1 个任务" in markdown
        assert "另有" not in markdown, "无 harness_invalid_rows 键的旧输出不得新增披露"


class TestRowCaliber:
    def test_gate_row_keeps_none_attribution(self) -> None:
        row = _gate_row()

        assert row["harness_invalid"] is True
        for key in ("failure_bucket", "failure_bucket_detail", "attribution_edge", "attribution_fault_side"):
            assert row[key] is None, f"门禁行没有终局状态可分类，{key} 不得臆造"

    def test_gate_producer_wiring_feeds_exclusion(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            rb,
            "_check_swe_bench_p2p_gate",
            lambda task: {"harness_invalid": True, "error_type": "p2p_low", "details": {}},
        )
        row = rb.run_single_task(_make_task(), ["aitester"], str(tmp_path))["aitester"]

        assert row["harness_invalid"] is True
        summary = _aggregate_failure_buckets([row, _crash_row()])
        assert summary["harness_invalid_rows"] == 1
        assert summary["unclassified_rows"] == 1
        assert summary["total"] == 0
