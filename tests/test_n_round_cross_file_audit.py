"""D3（N-5）回归锁：跨文件结果行审计字段（成功/失败分支键位一致）。

背景（N-4 item03 实测 D3，P2）
-----------------------------
synthetic level3 跨文件任务的结果行**不含** `cross_file_deps`（依赖图只在
`_dump_state_artifacts` 的 raw 落盘）——"跨文件修复路径是否被触达、依赖图是否
为空"无法从批次工件逐行审计。

N-5 修复：`experiments/run_benchmark._build_task_result` 的成功/失败两分支统一
展开 `_cross_file_audit_fields(...)`，新增三键（纯观测，不改判分口径）：
- `cross_file_enabled`：本行运行时 `CROSS_FILE_ENABLE` 是否开启（bool；异常 None）；
- `cross_file_deps`：终态依赖边列表（成功分支取 state；失败分支/无状态 None）；
- `cross_file_plan_present`：终态是否产出多文件修复计划（失败分支恒 False）。

本文件锁定：helper 语义、env 开关反映、成功/失败结果行键位一致、无状态不臆造、
以及"纯新增不改既有判分字段"。
"""

from __future__ import annotations

import pytest

from experiments.run_benchmark import _build_task_result, _cross_file_audit_fields
from src.datasets.dataset_loader import BenchmarkTask


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="synthetic__crossfile_d3",
        repo_name="synthetic",
        problem_statement="cross-file D3 audit probe",
        instance_code="def f():\n    return 1\n",
        test_code="",
        expected_pass_count=0,
        total_test_count=0,
        metadata={},
    )


_AUDIT_KEYS = {"cross_file_enabled", "cross_file_deps", "cross_file_plan_present"}


class TestCrossFileAuditHelper:
    def test_none_state_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """失败分支（无终态）：enabled 随运行时开关、deps None、plan_present False。"""
        monkeypatch.delenv("CROSS_FILE_ENABLE", raising=False)
        fields = _cross_file_audit_fields(None)
        assert set(fields) == _AUDIT_KEYS
        assert fields["cross_file_enabled"] is False
        assert fields["cross_file_deps"] is None
        assert fields["cross_file_plan_present"] is False

    def test_enabled_flag_reflects_runtime_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        assert _cross_file_audit_fields(None)["cross_file_enabled"] is True
        monkeypatch.setenv("CROSS_FILE_ENABLE", "false")
        assert _cross_file_audit_fields(None)["cross_file_enabled"] is False

    def test_enabled_flag_exception_degrades_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """读取异常不阻断结果构造：enabled 记 None（可审计"未知"而非静默 False）。"""

        def _boom() -> bool:
            raise RuntimeError("cross_file env probe failed")

        monkeypatch.setattr("src.tools.cross_file.cross_file_enabled", _boom)
        assert _cross_file_audit_fields(None)["cross_file_enabled"] is None

    def test_success_state_deps_and_plan_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        final_state = {
            "cross_file_deps": [{"source_module": "module_a", "target_module": "module_b", "import_name": "compute"}],
            "cross_file_plan": {"target_modules": ["module_b"], "patches": [{"module": "module_b"}]},
        }
        fields = _cross_file_audit_fields(final_state)
        assert fields["cross_file_deps"] == final_state["cross_file_deps"]
        assert fields["cross_file_plan_present"] is True

    def test_success_state_empty_plan_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        final_state = {"cross_file_deps": [], "cross_file_plan": None}
        fields = _cross_file_audit_fields(final_state)
        assert fields["cross_file_deps"] == []
        assert fields["cross_file_plan_present"] is False

    def test_malformed_deps_not_trusted(self) -> None:
        """state 被污染（deps 非 list）时不把脏数据写进行：保守 None。"""
        fields = _cross_file_audit_fields({"cross_file_deps": {"bad": "shape"}, "cross_file_plan": {}})
        assert fields["cross_file_deps"] is None

    def test_helper_does_not_mutate_state(self) -> None:
        final_state = {"cross_file_deps": [{"source_module": "a", "target_module": "b"}], "cross_file_plan": {"x": 1}}
        snapshot = dict(final_state)
        _cross_file_audit_fields(final_state)
        assert final_state == snapshot


class TestResultRowParity:
    """成功/失败分支结果行必须带同一组审计键（D3 核心要求）。"""

    def _failure_row(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        monkeypatch.delenv("CROSS_FILE_ENABLE", raising=False)
        return _build_task_result(_make_task(), 0.1, None, diagnosis="probe", error_category="error")

    def _success_row(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        final_state = {
            "task_id": "synthetic__crossfile_d3",
            "cross_file_deps": [{"source_module": "module_a", "target_module": "module_b"}],
            "cross_file_plan": {"target_modules": ["module_b"]},
        }
        return _build_task_result(_make_task(), 0.1, final_state)

    def test_failure_branch_has_audit_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = self._failure_row(monkeypatch)
        assert set(row) >= _AUDIT_KEYS
        assert row["cross_file_enabled"] is False
        assert row["cross_file_deps"] is None
        assert row["cross_file_plan_present"] is False

    def test_success_branch_has_audit_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = self._success_row(monkeypatch)
        assert set(row) >= _AUDIT_KEYS
        assert row["cross_file_enabled"] is True
        assert row["cross_file_deps"] == [{"source_module": "module_a", "target_module": "module_b"}]
        assert row["cross_file_plan_present"] is True

    def test_success_and_failure_key_sets_identical_for_audit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """成功/失败分支键位一致（D3 明确要求；只比审计三键，不动历史键集合）。"""
        failure = self._failure_row(monkeypatch)
        success = self._success_row(monkeypatch)
        assert {key: key in failure for key in _AUDIT_KEYS} == {key: True for key in _AUDIT_KEYS}
        assert set(failure) >= _AUDIT_KEYS
        assert set(success) >= _AUDIT_KEYS

    def test_scoring_fields_unchanged_by_audit_additions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """纯新增审计字段不得改变判分/既有列语义（失败分支 passed=False 等）。"""
        row = self._failure_row(monkeypatch)
        assert row["passed"] is False
        assert row["coverage"] == 0.0
        assert row["stop_reason"] is None
