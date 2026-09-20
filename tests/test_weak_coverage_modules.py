"""
5.1 弱覆盖模块补强测试。

运行：
    pytest tests/test_weak_coverage_modules.py -v
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ─── cli_output: print_rich_table 边界 ────────────────────────────────────

class TestCliOutputBoundary:
    """5.1 cli_output 弱覆盖补强：print_rich_table 边界用例。"""

    def test_print_rich_table_empty_list(self, capsys):
        """空列表：不崩溃。"""
        from src.cli.output import print_rich_table

        print_rich_table([])
        captured = capsys.readouterr()
        assert captured.out is not None or captured.err is not None

    def test_print_rich_table_single_result(self, capsys):
        """单条结果：正常渲染。"""
        from src.cli.output import print_rich_table

        print_rich_table([{"status": "PASS", "file": "test_a.py", "function": "test_x"}])
        captured = capsys.readouterr()
        # rich 渲染到 stdout 或 stderr；"test_a.py" 必须出现在其中之一（此前 or True 恒真，断言形同虚设）
        assert "test_a.py" in captured.out or "test_a.py" in captured.err

    def test_print_rich_table_missing_fields(self, capsys):
        """字段缺失：容错处理，不崩溃。"""
        from src.cli.output import print_rich_table

        print_rich_table([{"status": "FAIL"}])
        # 不抛异常即可
        captured = capsys.readouterr()
        assert captured.out is not None or captured.err is not None


# ─── error_classifier: 新分类路径 ────────────────────────────────────────

class TestErrorClassifierNewCategories:
    """5.1 error_classifier 弱覆盖补强：PATCH_VALIDATION_FAILED / RAG_RETRIEVAL_EMPTY。"""

    def test_patch_validation_failed_category(self):
        """repair_history 中 patch_applied=False → refine 为 PATCH_VALIDATION_FAILED。"""
        from src.agents.error_classifier import refine_failure_category

        result = refine_failure_category(
            "unknown",
            False,
            repair_history=[{"patch_applied": False}],
        )
        assert result == "patch_validation_failed", f"实际: {result}"

    def test_rag_retrieval_empty_category(self):
        """rag_stats 非空但全部 results=0 → refine 为 RAG_RETRIEVAL_EMPTY。"""
        from src.agents.error_classifier import refine_failure_category

        result = refine_failure_category(
            "assertion",
            False,
            repair_history=[{"patch_applied": True}],
            rag_stats=[{"results": 0, "max_similarity": 0.1}],
        )
        assert result == "rag_retrieval_empty", f"实际: {result}"

    def test_passed_task_unchanged(self):
        """成功任务原样返回传入类别。"""
        from src.agents.error_classifier import refine_failure_category

        result = refine_failure_category("assertion", True)
        assert result == "assertion"

    def test_neither_triggered_returns_original(self):
        """补丁通过 + RAG 有命中 → 原样返回传入类别。

        注意：5.2 起需传非空 execution_trace，否则会被细化为
        EXECUTION_TRACE_MISSING（空轨迹 = 执行器异常路径标识）。
        """
        from src.agents.error_classifier import refine_failure_category

        result = refine_failure_category(
            "index",
            False,
            repair_history=[{"patch_applied": True}],
            rag_stats=[{"results": 3, "max_similarity": 0.8}],
            execution_trace=[{"iteration": 0, "passed": False}],
        )
        assert result == "index"

    def test_refine_final_error_category(self):
        """refine_final_error_category 封装函数：传 dict 提取并细化。"""
        from src.agents.error_classifier import refine_final_error_category

        state = {
            "error_category": "unknown",
            "test_passed": False,
            "repair_history": [{"patch_applied": False}],
            "rag_stats": [],
        }
        result = refine_final_error_category(state)
        assert result == "patch_validation_failed", f"实际: {result}"

    def test_refine_final_empty_state(self):
        """空状态 dict：安全默认，不抛 KeyError。

        5.2 起空状态（test_passed 缺省 False + execution_trace 缺省 None）
        被细化为 EXECUTION_TRACE_MISSING（而非旧版的空串）——这是 5.2 的
        预期行为（空轨迹视为执行器异常路径，需单独标识）。
        """
        from src.agents.error_classifier import refine_final_error_category

        result = refine_final_error_category({})
        assert result == "execution_trace_missing", f"实际: {result}"


# ─── executor_runtime: 清理路径与重试异常分支 ────────────────────────────

class TestExecutorRuntimeCleanup:
    """5.1 executor_runtime 弱覆盖补强：cleanup 路径与异常分支。"""

    def test_cleanup_temp_file_removes_existing(self, tmp_path):
        """cleanup_temp_file 删除存在的文件。"""
        from src.agents.executor_runtime import cleanup_temp_file

        target = tmp_path / "test_tmp.py"
        target.write_text("code")
        cleanup_temp_file(str(target))
        assert not target.exists()

    def test_cleanup_temp_file_missing_no_crash(self, tmp_path):
        """cleanup_temp_file 对不存在的文件不崩溃。"""
        from src.agents.executor_runtime import cleanup_temp_file

        cleanup_temp_file(str(tmp_path / "does_not_exist.py"))
        # 不抛异常即可

    def test_cleanup_sandbox_removes_directory(self, tmp_path):
        """cleanup_sandbox 删除沙箱目录。"""
        from src.agents.executor_runtime import cleanup_sandbox

        sandbox = tmp_path / "sandbox_dir"
        sandbox.mkdir()
        (sandbox / "file.py").write_text("x = 1")
        cleanup_sandbox(str(sandbox))
        assert not sandbox.exists()

    def test_cleanup_sandbox_missing_no_crash(self, tmp_path):
        """cleanup_sandbox 对不存在的目录不崩溃。"""
        from src.agents.executor_runtime import cleanup_sandbox

        cleanup_sandbox(str(tmp_path / "no_such_dir"))
        # 不抛异常即可

    def test_run_pytest_with_retry_timeout_returns_early_return(self, tmp_path, monkeypatch):
        """超时分支：subprocess.run 抛 TimeoutExpired → EARLY_RETURN 标记。"""
        from src.agents.executor_runtime import run_pytest_with_retry

        class FakeSelf:
            timeout = 1

        # mock subprocess.run 抛出 TimeoutExpired
        import subprocess as sp
        timeout_exc = sp.TimeoutExpired(
            cmd="pytest", output="partial", stderr="err", timeout=1
        )
        with monkeypatch.context() as mp:
            mp.setattr(sp, "run", lambda *a, **k: (_ for _ in ()).throw(timeout_exc))
            output, result = run_pytest_with_retry(FakeSelf(), ["pytest"], {}, str(tmp_path))
        assert result[0] == "EARLY_RETURN"
        assert result[1]["type"] == "timeout"
        assert "partial" in output

    def test_run_pytest_with_retry_permission_error(self, tmp_path, monkeypatch):
        """权限错误分支：subprocess.run 抛 PermissionError → EARLY_RETURN。"""
        from src.agents.executor_runtime import run_pytest_with_retry

        class FakeSelf:
            timeout = 1

        import subprocess as sp
        perm_exc = PermissionError("permission denied")
        monkeypatch.setattr(sp, "run", lambda *a, **k: (_ for _ in ()).throw(perm_exc))
        _output, result = run_pytest_with_retry(FakeSelf(), ["pytest"], {}, str(tmp_path))
        assert result[0] == "EARLY_RETURN"
        assert result[1]["type"] == "permission_error"

    def test_run_pytest_with_retry_generic_exception_breaks_loop(self, tmp_path, monkeypatch):
        """通用 Exception 分支：记录后 break，返回 (error_msg, None)。"""
        from src.agents.executor_runtime import run_pytest_with_retry

        class FakeSelf:
            timeout = 1

        import subprocess as sp
        with monkeypatch.context() as mp:
            mp.setattr(sp, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
            output, result = run_pytest_with_retry(FakeSelf(), ["pytest"], {}, str(tmp_path))
        # 通用异常：break 后 last_result=None，output 为错误消息
        assert result is None
        assert "boom" in output


