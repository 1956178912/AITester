"""BR 轮（2026-10-22 第三方集中复审）N01/N09：探针隔离与帧选择。

N01：探针只在宿主解释器执行；主执行用 Docker/内核沙箱、或已因隔离不可用
被拒绝时，重放等于把执行降级为无隔离宿主执行。修复后 `capture_failure_snapshot`
按 `backend` 拒绝，`nodes._runtime_probe_backend` 负责从执行结果推导真实档位。

N09：历史 runner 只保留最内层一帧，父进程又只允许探针文件帧——测试在被测模块
内部抛出时唯一有效帧被清空。修复后保留完整异常链，并按真实目标路径选帧。
"""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import runtime_probe
from src.agents.runtime_probe import capture_failure_snapshot


class _FakeAgent:
    def __init__(self, *, use_docker=False, use_venv=False, kernel=None):
        self.use_docker = use_docker
        self.use_venv = use_venv
        self._kernel_sandbox_executable = kernel


class TestProbeIsolationGuard:
    @pytest.mark.parametrize("backend", ["docker", "kernel", "refused", "unknown", ""])
    def test_non_host_backend_refuses_without_subprocess(self, backend, monkeypatch):
        """N01：隔离级别不匹配 → 不启动子进程（不是"降级后返回 None"）。"""
        import src.utils.process_utils as pu

        def _boom(*a, **k):
            raise AssertionError("隔离级别不匹配时不得启动宿主探针子进程")

        monkeypatch.setattr(pu, "run_with_timeout", _boom)

        assert capture_failure_snapshot("def test_x():\n    assert 1 == 2\n", backend=backend) is None

    def test_local_backend_still_runs(self, tmp_path):
        """对照：local 档位保持原行为（能拿到快照）。"""
        target = tmp_path / "foo.py"
        target.write_text("def boom():\n    x = 1\n    raise ValueError('inner')\n", encoding="utf-8")
        code = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(tmp_path)!r})
            from foo import boom

            def test_boom():
                boom()
            """
        )

        snapshot = capture_failure_snapshot(code, target_module="foo", target_file=str(target), backend="local")

        assert snapshot is not None
        assert snapshot["frames"]


class TestProbeBackendDerivation:
    @pytest.mark.parametrize(
        ("agent", "result", "expected"),
        [
            (_FakeAgent(), {"error_info": {"type": "docker_unavailable"}}, "refused"),
            (_FakeAgent(), {"error_info": {"type": "kernel_sandbox_unavailable"}}, "refused"),
            (_FakeAgent(use_docker=True), {}, "docker"),
            (_FakeAgent(kernel="sandbox-exec"), {}, "kernel"),
            (_FakeAgent(use_venv=True), {}, "venv"),
            (_FakeAgent(), {}, "local"),
            # R01（2026-10-23 全量集中复审 P1）：executor 返回前已清除实例级
            # _kernel_sandbox_executable / _kernel_sandbox_obs，真实交接只携带
            # 不可变 result["kernel_sandbox_obs"]——必须据此判 kernel，不得回落
            # local/venv 让探针以宿主解释器重放。
            (
                _FakeAgent(),
                {"kernel_sandbox_obs": {"backend": "seatbelt", "supported": True}},
                "kernel",
            ),
            (
                _FakeAgent(),
                {"kernel_sandbox_obs": {"backend": "landlock_bwrap", "supported": True}},
                "kernel",
            ),
            # venv 配置也不能覆盖 result 中的内核沙箱执行证据
            (
                _FakeAgent(use_venv=True),
                {"kernel_sandbox_obs": {"backend": "seatbelt", "supported": True}},
                "kernel",
            ),
            # backend=none / supported=False 的观测层不代表内核沙箱实际生效
            (_FakeAgent(), {"kernel_sandbox_obs": {"backend": "none", "supported": False}}, "local"),
            (_FakeAgent(), {"kernel_sandbox_obs": {"backend": "seatbelt", "supported": False}}, "local"),
            # 内核观测存在但显式隔离拒绝仍优先 refused（T4：不可用即拒绝）
            (
                _FakeAgent(),
                {
                    "error_info": {"type": "kernel_sandbox_unavailable"},
                    "kernel_sandbox_obs": {"backend": "seatbelt", "supported": True},
                },
                "refused",
            ),
        ],
    )
    def test_backend_matrix(self, agent, result, expected):
        from src.graph.nodes import _runtime_probe_backend

        assert _runtime_probe_backend(agent, result) == expected


class TestProbeFrameSelection:
    def test_target_module_frame_survives_filter(self, tmp_path):
        """N09：异常在被测模块内部抛出，目标帧不得被探针文件过滤清掉。"""
        target = tmp_path / "foo.py"
        target.write_text(
            "def boom():\n    value = 41\n    raise ValueError('inner boom')\n",
            encoding="utf-8",
        )
        code = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(tmp_path)!r})
            from foo import boom

            def test_boom():
                boom()
            """
        )

        snapshot = capture_failure_snapshot(code, target_module="foo", target_file=str(target), backend="local")

        assert snapshot is not None
        files = [os.path.basename(fr.get("file", "")) for fr in snapshot["frames"]]
        assert "foo.py" in files  # 真实目标模块帧被保留
        assert any(fr.get("function") == "boom" for fr in snapshot["frames"])
        # 快照上限不因链路变长而膨胀（对外契约 _MAX_PROBE_FRAMES）
        assert len(snapshot["frames"]) <= runtime_probe._MAX_PROBE_FRAMES

    def test_empty_snapshot_when_only_foreign_frames(self, tmp_path):
        """目标不相关的帧仍被过滤（避免把库内部帧当被测失败证据）。"""
        target = tmp_path / "foo.py"
        target.write_text("def unused():\n    return 1\n", encoding="utf-8")
        code = textwrap.dedent(
            """
            def test_raise_here():
                raise RuntimeError("test-level failure")
            """
        )

        snapshot = capture_failure_snapshot(code, target_module="foo", target_file=str(target), backend="local")

        # 探针文件帧（test_raise_here）属于测试自身，保留；不相关外部帧不入快照
        assert snapshot is not None
        assert all(os.path.basename(fr["file"]) in ("foo_probe.py", "foo.py") for fr in snapshot["frames"])


class TestOtelNonObjectRecords:
    """N10：合法 JSON 但非对象的行不得让整文件导出崩溃。"""

    def test_null_line_is_isolated_with_line_number(self, caplog):
        import logging
        from unittest.mock import mock_open, patch

        from src.observability.otel_export import export_trace_jsonl

        payload = '{"event": "task_start", "run_id": "abcdef0123456789abcdef0123456789"}\nnull\n{"event": "node", "node": "executor"}\n'
        with patch("builtins.open", mock_open(read_data=payload)), caplog.at_level(logging.WARNING):
            spans = export_trace_jsonl("in_memory.trace.jsonl")

        assert spans  # 未抛 AttributeError，其余记录照常导出
        assert any("第 2 行" in rec.message and "NoneType" in rec.message for rec in caplog.records)

    @pytest.mark.parametrize("bad", ["[]", "0", "false", '"text"'])
    def test_all_non_object_shapes_skipped(self, bad):
        from unittest.mock import mock_open, patch

        from src.observability.otel_export import export_trace_jsonl

        payload = f'{{"event": "task_start"}}\n{bad}\n{{"event": "node"}}\n'
        with patch("builtins.open", mock_open(read_data=payload)):
            spans = export_trace_jsonl("in_memory.trace.jsonl")

        assert spans


class TestCallScopeIsolation:
    """N11：并发专家共享任务账本时，缓存计量必须按调用作用域隔离。"""

    def test_concurrent_scopes_do_not_cross_count(self):
        import threading

        from src.budget.token_usage import (
            attach_usage,
            begin_call_scope,
            call_scope_tokens,
            get_usage,
            record_usage,
            reset,
        )

        reset()
        usage = get_usage()
        barrier = threading.Barrier(2)
        results: dict[str, int | None] = {}

        def worker(name: str, inp: int, out: int) -> None:
            attach_usage(usage)
            begin_call_scope()
            barrier.wait()  # 两个作用域都已开始（旧口径下 before 读数相同）
            record_usage(inp, out, model="m")
            barrier.wait()
            results[name] = call_scope_tokens()

        threads = [
            threading.Thread(target=worker, args=("A", 4, 6)),
            threading.Thread(target=worker, args=("B", 8, 12)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert results == {"A": 10, "B": 20}  # 不是共享总量 30
        assert usage.total_tokens == 30  # 任务总账仍完整

    def test_rejection_marks_scope_partial(self):
        from src.budget.token_usage import (
            begin_call_scope,
            call_scope_had_rejection,
            call_scope_tokens,
            record_usage,
            reset,
        )

        reset()
        begin_call_scope()
        assert record_usage("100", 5, model="m")  # 拒绝
        assert call_scope_tokens() == 0
        assert call_scope_had_rejection() is True

    def test_end_scope_clears_state(self):
        from src.budget.token_usage import begin_call_scope, call_scope_tokens, end_call_scope

        begin_call_scope()
        end_call_scope()
        assert call_scope_tokens() is None
