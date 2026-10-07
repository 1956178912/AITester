"""AM 批次（2026-10-06 第十三轮审查落地续）测试。

锁定三组行为：
- AM1a 预算实例级 token cap：set_task_token_cap 注入后 check_budget
  自动生效（无需 COST_BUDGET_ENABLE）、超限拒绝、reset_budget 清除、
  cap 跟随 BudgetSnapshot 实例（attach_budget 跨线程传播）、as_dict
  含 token_cap_override 观测键；
- AM1b/c CLI 透传链：parse_per_task_token_caps 解析与 fail-fast、
  run_single_task 签名含 per_task_token_caps、run_main_batch 参数
  与 rb.run_benchmark 调用透传、结果行 token_budget_capped 字段；
- AM2 预注册一致性：E6 节引用实现旗标名 --per-task-token-caps
  （zh/en）、执行记录表含 E6/E7 行、就绪命令含 E6 命令块。
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

from src.budget import cost_budget as cb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREREG_ZH = (PROJECT_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
PREREG_EN = (PROJECT_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_thread_budget():
    """每用例前后清线程预算累计器，防线程局部残留串扰。"""
    cb.reset_budget()
    yield
    cb.reset_budget()


class TestTaskTokenCap:
    """AM1a：预算实例级 token cap 语义。"""

    def test_cap_activates_check_without_env_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        # 无 cap：预算关 → 恒放行（历史口径）
        assert cb.check_budget(consumed_delta_tokens=10_000) is True
        # 注入 cap=100：同量消耗被拒（cap 自动生效，无需 env 开关）
        cb.set_task_token_cap(100)
        assert cb.current_budget().token_cap_override == 100
        assert cb.check_budget(consumed_delta_tokens=10_000) is False
        assert cb.current_budget().exceeded is True

    def test_cap_boundary_not_exceeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        cb.set_task_token_cap(1_000)
        assert cb.check_budget(consumed_delta_tokens=999) is True
        assert cb.current_budget().exceeded is False

    def test_reset_budget_clears_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        cb.set_task_token_cap(50)
        cb.check_budget(consumed_delta_tokens=1_000)
        cb.reset_budget()
        assert cb.current_budget().token_cap_override == 0
        assert cb.current_budget().exceeded is False
        assert cb.check_budget(consumed_delta_tokens=1_000) is True

    def test_negative_cap_clamped_to_zero(self) -> None:
        cb.set_task_token_cap(-5)
        assert cb.current_budget().token_cap_override == 0

    def test_cap_follows_instance_across_threads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """C8 语义：cap 写在 BudgetSnapshot 实例上，attach_budget 传播。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        cb.set_task_token_cap(10)
        snapshot = cb.current_budget()

        observed: dict[str, object] = {}

        def worker() -> None:
            cb.attach_budget(snapshot)
            observed["allowed"] = cb.check_budget(consumed_delta_tokens=500)

        import threading

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert observed["allowed"] is False

    def test_as_dict_exposes_override(self) -> None:
        cb.set_task_token_cap(4_223)
        stats = cb.get_budget_stats()
        assert stats["token_cap_override"] == 4_223

    def test_env_limit_still_works_without_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 cap 时 env 口径不变（COST_BUDGET_ENABLE + COST_BUDGET_TOKENS）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100")
        assert cb.check_budget(consumed_delta_tokens=150) is False


class TestParseCaps:
    """AM1b：parse_per_task_token_caps 解析与 fail-fast。"""

    def test_parses_multi_arm(self) -> None:
        from experiments.run_benchmark import parse_per_task_token_caps

        assert parse_per_task_token_caps("aitester=4223,plain_llm_df=26115") == {
            "aitester": 4223,
            "plain_llm_df": 26115,
        }

    @pytest.mark.parametrize(
        "spec",
        [None, "", "  "],
    )
    def test_empty_returns_no_caps(self, spec: str | None) -> None:
        from experiments.run_benchmark import parse_per_task_token_caps

        assert parse_per_task_token_caps(spec) == {}

    @pytest.mark.parametrize(
        "bad",
        [
            "unknown_arm=100",  # 未知臂
            "aitester=0",  # 非正整数
            "aitester=-3",  # 负数
            "aitester=abc",  # 非整数
            "aitester",  # 缺 =
        ],
    )
    def test_invalid_specs_fail_fast(self, bad: str) -> None:
        from experiments.run_benchmark import parse_per_task_token_caps

        with pytest.raises(ValueError):
            parse_per_task_token_caps(bad)


class TestPlumbing:
    """AM1b/c：签名与透传链（行为级检查，非源码文本断言）。"""

    def test_run_single_task_signature(self) -> None:
        from experiments.run_benchmark import run_single_task

        assert "per_task_token_caps" in inspect.signature(run_single_task).parameters

    def test_run_benchmark_signature(self) -> None:
        from experiments.run_benchmark import run_benchmark

        assert "per_task_token_caps" in inspect.signature(run_benchmark).parameters

    def test_sliding_window_signature(self) -> None:
        from experiments.run_benchmark import _run_tasks_sliding_window

        params = inspect.signature(_run_tasks_sliding_window).parameters
        assert "per_task_token_caps" in params
        assert params["per_task_token_caps"].default is None

    def test_run_task_with_progress_accepts_six_tuple(self) -> None:
        """旧 5 元组兼容 + 新 6 元组（caps 位）都可达 run_single_task。"""
        from experiments import run_benchmark as rb

        sent: dict[str, object] = {}

        def fake_run_single_task(task, baselines, output_dir, verbose, save_state=False, per_task_token_caps=None):
            sent["caps"] = per_task_token_caps
            return {}

        original = rb.run_single_task
        rb.run_single_task = fake_run_single_task  # type: ignore[assignment]
        try:
            rb._run_task_with_progress(("t", ["aitester"], "/tmp", False, False))
            assert sent["caps"] is None  # 旧 5 元组
            rb._run_task_with_progress(("t", ["aitester"], "/tmp", False, False, {"aitester": 4223}))
            assert sent["caps"] == {"aitester": 4223}  # 新 6 元组
        finally:
            rb.run_single_task = original  # type: ignore[assignment]

    def test_run_main_batch_passes_caps(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_main_batch 的 argparse 参数与 rb.run_benchmark 调用透传。"""
        import experiments.run_benchmark as rbmod
        import experiments.run_main_batch as mb

        captured: dict[str, object] = {}

        def fake_run_benchmark(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {}

        monkeypatch.setattr(rbmod, "run_benchmark", fake_run_benchmark)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_main_batch.py",
                "--task-count",
                "2",
                "--per-task-token-caps",
                "aitester=4223",
                "--allow-dirty",
                "--skip-stats",
                "--output-dir",
                str(tmp_path / "am_out"),
            ],
        )
        mb.main()  # 空 out_dir 无批次文件 → 定位警告后提前 return，不触统计
        assert captured.get("per_task_token_caps") == "aitester=4223"

    def test_result_row_has_capped_field(self) -> None:
        """_build_task_result 失败分支透出 token_budget_capped（键集合同构）。"""
        from src.budget.cost_budget import BudgetSnapshot
        from src.datasets.dataset_loader import BenchmarkTask

        cb._thread_local.budget = BudgetSnapshot()
        cb.set_task_token_cap(10)
        task = BenchmarkTask(
            task_id="task_am0001",
            repo_name="synthetic",
            problem_statement="p",
            instance_code="x = 1\n",
            test_code="",
            expected_pass_count=1,
            total_test_count=1,
            metadata={},
        )
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(task, 0.1, final_state=None, diagnosis="d", error_category="runtime")
        assert isinstance(row["token_budget_capped"], bool)
        assert row["token_budget_capped"] is False  # 未消费不超限


class TestPreregConsistency:
    """AM2：预注册 E6 与实现旗标名/表行一致。"""

    def test_flag_name_matches_implementation(self) -> None:
        # 实现旗标为复数形式 --per-task-token-caps；旧单数名不得再出现在
        # E6 节（防"文档与 CLI 不一致"复现 AL1 类耦合事故）
        for text in (PREREG_ZH, PREREG_EN):
            assert "--per-task-token-caps" in text
            assert "--per-task-token-cap " not in text
            assert "--per-task-token-cap`" not in text

    def test_execution_log_has_e6_e7_rows(self) -> None:
        assert "E6 | 待执行" in PREREG_ZH
        # AO 批（2026-10-07）：E7 候选清单已生成，状态推进为"待人工复核"
        assert "E7 | 待人工复核（候选清单已生成，AO 批）" in PREREG_ZH
        assert "E6 | pending" in PREREG_EN
        assert "E7 | pending manual review (candidate list generated, batch AO)" in PREREG_EN

    def test_ready_commands_have_e6_block(self) -> None:
        assert "### E6 就绪命令" in PREREG_ZH
        assert "### E6 ready commands" in PREREG_EN
        # AO 批（2026-10-07）E6 cap 来源修订：matched 上限改取 E2 实测均值
        # （shell 占位变量注入）；R-P0-2 旧常数 4223/26115 不得再以字面
        # cap 形式出现（防无门控口径硬编码复发）
        assert '--per-task-token-caps "aitester=${DF_MEAN}"' in PREREG_ZH
        assert '--per-task-token-caps "plain_llm_df=${AITESTER_MEAN}"' in PREREG_EN
        assert "aitester=4223" not in PREREG_ZH
        assert "plain_llm_df=26115" not in PREREG_EN
