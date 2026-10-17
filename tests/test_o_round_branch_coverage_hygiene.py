#!/usr/bin/env python3
"""O 轮运行期卫生：branch coverage 测量子进程的"挂死 + 父死亡"双缺口回归。

背景（O 轮现场）：
- N 轮后残留一个 **ppid=1、99% CPU、龄期 82 分钟**的孤儿进程：`_MEASURE_SCRIPT`
  在 QuixBugs 非终止家族（bitcount 等）的生成测试上让 pytest 永久挂起；
- 历史上只有外层 `run_with_timeout` 的 60s 超时兜底，且该调用点未启用
  `orphan_guard`——调用方进程被外部杀死后，子进程被 init 收养继续空转。
- 修复：① 测量子进程内 pytest-timeout 单测 10s（插件缺失自动降级）；
  ② 调用点 `orphan_guard=True` 父死回收；③ 既有 60s 外层超时不变。

本文件锁住"不允许回退"的关键形态（静态常量/脚本片段 + 行为边界 + 传参）。
"""

from __future__ import annotations

import time
from pathlib import Path

from src.tools import branch_coverage_inject as bci

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestNoRegressionStaticLocks:
    def test_per_test_timeout_constant(self):
        assert bci._PER_TEST_TIMEOUT_SECONDS == 10

    def test_measure_script_has_pytest_timeout(self):
        # 子进程内 pytest 单测超时：插件可用时启用，缺失时自动降级（不得写死必装）
        assert "pytest_timeout" in bci._MEASURE_SCRIPT
        assert "'--timeout=10'" in bci._MEASURE_SCRIPT
        assert "except ImportError" in bci._MEASURE_SCRIPT

    def test_outer_timeout_unchanged(self):
        # 外层 60s 兜底不变（双层防护：内层 10s/测 + 外层 60s 进程组）
        assert bci._MEASURE_TIMEOUT == 60

    def test_no_new_env_vars(self):
        # 修复只引入常量，未新增 env 开关（避免 env 预算/快照门禁漂移）
        assert "BRANCH_COVERAGE_INJECT_PER_TEST" not in Path(bci.__file__).read_text(encoding="utf-8")


class TestOrphanGuardWired:
    def test_call_site_passes_orphan_guard_true(self, monkeypatch, tmp_path):
        captured: dict = {}

        class _FakeProc:
            returncode = 1
            timed_out = False
            stdout = ""
            stderr = ""

        def fake_run_with_timeout(args, **kwargs):
            captured.update(kwargs)
            return _FakeProc()

        monkeypatch.setattr(bci, "run_with_timeout", fake_run_with_timeout)
        target = tmp_path / "m.py"
        target.write_text("def f(x):\n    return x\n", encoding="utf-8")
        bci.measure_branch_coverage(str(target), "def test_f():\n    pass\n", "m", cwd=str(tmp_path))
        assert captured.get("orphan_guard") is True, "父死亡看门狗未接到 branch 测量调用点"
        assert captured.get("timeout") == bci._measure_timeout()

    def test_measure_returns_none_on_timeout(self, monkeypatch, tmp_path):
        class _TimeoutProc:
            returncode = 124
            timed_out = True

        monkeypatch.setattr(bci, "run_with_timeout", lambda *a, **k: _TimeoutProc())
        target = tmp_path / "m.py"
        target.write_text("def f(x):\n    return x\n", encoding="utf-8")
        assert bci.measure_branch_coverage(str(target), "def test_f():\n    pass\n", "m", cwd=str(tmp_path)) is None


class TestHangingTestBounded:
    def test_infinite_loop_test_is_bounded(self, tmp_path):
        """生成测试含死循环时，测量必须在远小于外层 60s 的时间内返回（10s/测超时生效）。"""
        target = tmp_path / "mod.py"
        target.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        hanging_test = "from mod import f\n\n\ndef test_hang():\n    while True:\n        pass\n"
        started = time.perf_counter()
        result = bci.measure_branch_coverage(str(target), hanging_test, "mod", cwd=str(tmp_path))
        elapsed = time.perf_counter() - started
        # 内层 pytest-timeout 10s 应让子进程在 ~10-15s 内结束；没有它则会撞外层 60s
        assert elapsed < 45.0, f"死循环测试测量耗时 {elapsed:.1f}s，pytest-timeout 未生效"
        # 结果允许 None（超时降级）或空覆盖 dict——重点是"有界返回"，不是具体数值
        assert result is None or isinstance(result, dict)
