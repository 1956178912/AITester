"""EM 轮：批次 provenance 的停止原因词表必须与 `StopReason` 枚举同域。

缺陷族：R56 的 harness 披露块承诺「重试与停止规则」可从工件复核（读者
据此判定增益来自脚手架还是角色协作），但
`provenance.harness.retry_stop_rules.stop_reasons` 是一份手写字面量：工件
自述 7 个值，`StopReason` 枚举有 13 个，**6 个真实终止原因从未出现在任何
新批次的 harness 自述里**——`test_gen_diagnosis_early` / `test_gen_diagnosis`
/ `test_passed_converged` / `max_iterations_reached` / `coverage_stall` /
`recursion_limit`。其中 `recursion_limit` 是 EJ 轮刚从死映射接线为可落盘的
确定性崩溃原因（`experiments/run_benchmark.py::_failure_attribution_for_result`
经 `effective_stop_reason` 读它），工件却仍声明 harness 只会以旧 7 值停止。

既有 `tests/test_r56_harness_disclosure.py` 从未读生产块：它手工内联构造
一个等价小 dict（docstring 声称"经 `_build_harness_block` 口径验证"，但该
函数并不存在），与生产路径同形地漏掉了这条——读侧从自己手抄的写侧取证，
双方共谋把漂移锁成绿色。

修法口径：词表由 `StopReason` 枚举派生（单一事实源），新增枚举值自动进入
新批次工件；已归档的历史工件一字节不动（7 值自述是那些批次的时代事实）。
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.run_benchmark as rb
from src.graph.workflow import StopReason

#: EM 根因调查时工件自述缺失、枚举里真实存在的 6 个值（RED 面）
PREVIOUSLY_UNDISCLOSED = (
    "test_gen_diagnosis_early",
    "test_gen_diagnosis",
    "test_passed_converged",
    "max_iterations_reached",
    "coverage_stall",
    "recursion_limit",
)

#: 历史工件已声明过的 7 个值——读侧可依赖的向后兼容面（护栏）
LEGACY_DISCLOSED = (
    "test_passed",
    "max_iterations",
    "skip_debugger_repair_invalid",
    "test_defect_regeneration_cap",
    "budget_exceeded",
    "regression_detected",
    "unknown",
)


class _OfflineAPI:
    """`src.api.api_manager` 替身：任何调用直接抛错（零网络，探针只留 error）。"""

    instances: ClassVar[list[Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).instances.append(self)

    def call(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("offline-stub")


class _StubDataset:
    """空任务批次替身：`size` 非 0 以避开"空数据集 ⇒ 降级内置 examples"分支。"""

    size = 1
    tasks: ClassVar[list[Any]] = []
    strict_skipped_task_ids: ClassVar[list[str]] = []


@pytest.fixture()
def offline_batch(monkeypatch: pytest.MonkeyPatch):
    """零 LLM、零网络的 run_benchmark 环境（同 tests/test_bo_raw_readside_disclosure.py 口径）。"""

    def _run(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
        fake_module = types.ModuleType("src.api.api_manager")
        fake_module.APIManager = _OfflineAPI  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "src.api.api_manager", fake_module)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        monkeypatch.setattr(rb, "load_dataset", lambda *a, **k: _StubDataset())
        return rb.run_benchmark(
            dataset_name="swe_bench",
            baselines=["plain_llm"],
            output_dir=str(tmp_path),
            parallel=1,
            **kwargs,
        )

    return _run


def _declared_reasons(summary: dict[str, Any]) -> list[str]:
    return summary["provenance"]["harness"]["retry_stop_rules"]["stop_reasons"]


class TestVocabularyCoversEnumDomain:
    """工件自述词表必须覆盖 `StopReason` 全域（新增枚举值自动纳入）。"""

    def test_declared_vocabulary_equals_enum_values(self, offline_batch, tmp_path):
        declared = _declared_reasons(offline_batch(tmp_path))
        expected = [reason.value for reason in StopReason]

        assert declared == expected

    def test_six_previously_undisclosed_reasons_are_present(self, offline_batch, tmp_path):
        declared = set(_declared_reasons(offline_batch(tmp_path)))
        missing = sorted(set(PREVIOUSLY_UNDISCLOSED) - declared)

        assert not missing, f"工件未披露真实终止原因：{missing}"

    def test_recursion_limit_is_disclosed_after_ej_wiring(self, offline_batch, tmp_path):
        """EJ 已让 recursion_limit 可落盘；harness 自述不得仍说它不存在。"""
        assert "recursion_limit" in _declared_reasons(offline_batch(tmp_path))


class TestCaliberGuards:
    """口径护栏：词表是纯字符串、顺序确定、审计对象与内存态同值。"""

    def test_legacy_seven_reasons_remain_disclosed(self, offline_batch, tmp_path):
        declared = set(_declared_reasons(offline_batch(tmp_path)))

        assert set(LEGACY_DISCLOSED) <= declared, "历史读侧可依赖的旧值被删除"

    def test_values_are_plain_strings_in_enum_order_without_duplicates(self, offline_batch, tmp_path):
        declared = _declared_reasons(offline_batch(tmp_path))

        assert all(type(value) is str for value in declared), "Enum 实例混入会让工件序列化口径漂移"
        assert len(declared) == len(set(declared)), "词表出现重复值"
        enum_order = [reason.value for reason in StopReason]
        assert declared == [value for value in enum_order if value in set(declared)], "词表须按枚举定义顺序"

    def test_on_disk_artifact_matches_in_memory(self, offline_batch, tmp_path):
        """工件是审计对象：磁盘上的词表必须与内存态逐项相同。"""
        summary = offline_batch(tmp_path)
        on_disk = json.loads(next(tmp_path.glob("benchmark_*.json")).read_text(encoding="utf-8"))

        assert on_disk["provenance"]["harness"]["retry_stop_rules"]["stop_reasons"] == _declared_reasons(summary)
