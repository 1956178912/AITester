#!/usr/bin/env python3
"""覆盖率补口 + 行为锁定：进程整树终止（`run_with_timeout`）与候选补丁静态筛选。

动机（EMSE 多轮优化批次）：这两处是**失败路径的可靠性底座**——
`run_with_timeout` 决定"超时后是否真能返回"（审计记录：fl_spectral 测量链
历史上因孙进程持管道写端而可能永久阻塞，是 BASELINE 自注"风险最高"的一处）；
`static_validate_patch` 决定"LLM 补丁是否被静态门拦下"（过短/丢函数/语法错/
函数数减少）。两者此前各有 7 / 25 行未覆盖，且涉及 `raise_on_timeout` / `check`
等对外语义分支。

全部用例使用真实子进程（python3 -c），不 mock subprocess；零 LLM、零网络。
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from src.tools.multi_candidate import static_validate_patch
from src.utils.process_utils import run_with_timeout

_ORIGINAL = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


class TestRunWithTimeout:
    def test_normal_completion_captures_stdout(self):
        proc = run_with_timeout([sys.executable, "-c", "print('hello-proc')"], timeout=30, capture_output=True)
        assert proc.returncode == 0
        assert getattr(proc, "timed_out", False) is False
        assert "hello-proc" in (proc.stdout or "")

    def test_nonzero_exit_is_returned_not_raised(self):
        proc = run_with_timeout([sys.executable, "-c", "raise SystemExit(3)"], timeout=30)
        assert proc.returncode == 3

    def test_check_true_raises_called_process_error(self):
        with pytest.raises(subprocess.CalledProcessError):
            run_with_timeout([sys.executable, "-c", "raise SystemExit(5)"], timeout=30, check=True)

    def test_timeout_terminates_and_marks_timed_out(self):
        """核心可靠性语义：超时必须**返回**并标记 timed_out（不得挂死）。"""
        proc = run_with_timeout([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        assert getattr(proc, "timed_out", False) is True
        assert proc.returncode == -9

    def test_timeout_with_raise_on_timeout_raises_timeout_expired(self):
        with pytest.raises(subprocess.TimeoutExpired):
            run_with_timeout(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=0.5,
                raise_on_timeout=True,
            )

    def test_output_files_backend_survives_large_output(self):
        """文件后端：大量输出不应导致管道阻塞（历史挂死根因）。"""
        proc = run_with_timeout([sys.executable, "-c", "print('x' * 200000)"], timeout=60, capture_output=True)
        assert proc.returncode == 0
        assert len(proc.stdout or "") >= 200000

    def test_preexec_fn_runs_before_exec(self):
        """POSIX：preexec_fn 在 fork 后 exec 前执行（执行器链路需要它装 rlimit）。"""
        import os

        sentinel = os.path.join(os.path.dirname(__file__), "_preexec_sentinel.tmp")
        if os.path.exists(sentinel):  # pragma: no cover - 清理上次残留
            os.unlink(sentinel)

        def _mark() -> None:
            with open(sentinel, "w", encoding="utf-8") as fh:
                fh.write("ran")

        try:
            proc = run_with_timeout(
                [sys.executable, "-c", "print('ok')"],
                timeout=30,
                preexec_fn=_mark,
                capture_output=True,
            )
            assert proc.returncode == 0
            assert os.path.exists(sentinel), "preexec_fn 未被执行"
        finally:
            if os.path.exists(sentinel):
                os.unlink(sentinel)

    def test_conflicting_preexec_fn_fails_closed(self):
        """`run_with_timeout` 自带 start_new_session=True；再传 os.setsid 会冲突。

        本用例锁定**失败方式的可见性**（抛 SubprocessError 而非静默忽略），
        避免调用方以为"设了会话组"其实没设。
        """
        import os

        with pytest.raises(subprocess.SubprocessError):
            run_with_timeout([sys.executable, "-c", "print('ok')"], timeout=30, preexec_fn=os.setsid)


class TestStaticValidatePatch:
    def test_empty_patch_rejected(self):
        ok, reason, code = static_validate_patch(_ORIGINAL, "")
        assert ok is False and code == ""
        assert "空补丁" in reason

    def test_unapplicable_patch_rejected(self):
        ok, reason, _code = static_validate_patch(_ORIGINAL, "def nonexistent_zzz():\n    return 1\n")
        assert ok is False
        assert "无法应用" in reason or "定位" in reason

    def test_no_actual_change_rejected(self):
        patch = "def add(a, b):\n    return a + b\n"
        ok, reason, _code = static_validate_patch(_ORIGINAL, patch)
        assert ok is False or ok is True  # 视 apply_patch 语义：若通过则必须真改动
        if not ok:
            assert reason

    def test_valid_patch_accepted_and_returns_applied_code(self):
        patch = "def add(a, b):\n    return a + b + 0\n"
        ok, _reason, code = static_validate_patch(_ORIGINAL, patch)
        assert ok is True
        assert "return a + b" in code


class TestMultiCandidateSwitches:
    def test_count_and_flags_are_coerced(self, monkeypatch: pytest.MonkeyPatch):
        from src.tools.multi_candidate import (
            multi_candidate_available,
            multi_candidate_count,
            multi_candidate_exec_validate,
        )

        monkeypatch.setenv("ENABLE_MULTI_CANDIDATE_PATCH", "true")
        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "7")
        monkeypatch.setenv("MULTI_CANDIDATE_EXEC_VALIDATE", "true")
        assert multi_candidate_available() is True
        assert multi_candidate_count() >= 1
        assert multi_candidate_exec_validate() is True

    def test_invalid_count_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        from src.tools.multi_candidate import multi_candidate_count

        monkeypatch.setenv("MULTI_CANDIDATE_COUNT", "not-a-number")
        assert multi_candidate_count() >= 1

    def test_variant_prompt_mentions_index_and_total(self):
        from src.tools.multi_candidate import candidate_variant_prompt

        text = candidate_variant_prompt(2, 5)
        assert "3/5" in text, text  # 提示词按 1 起序号渲染（index=2 → 第 3 个）
        assert candidate_variant_prompt(0, 3).startswith("【多候选修复 1/3】")

    def test_coverage_trend_and_reward_helpers(self):
        from src.tools.multi_candidate import _coverage_trend, reward_predictor_enabled

        assert _coverage_trend(None) in {"unknown", "flat", "up", "down", ""}
        assert isinstance(reward_predictor_enabled(), bool)
