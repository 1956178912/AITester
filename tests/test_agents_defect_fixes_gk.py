"""agents 层三处实测缺陷的回归锁（GK 轮，2026-10-28）。

三处缺陷都由并行审计探针发现、本会话**逐条独立复现**后修复；每处都锁住
「修复前的错误行为」并配负对照（防止把判据改松）。

1. **确定性守卫漏检 `numpy.random`**（`src/agents/deterministic_guard.py`）
   - 别名展开写错位置：`parts[0] = _IMPORT_ALIASES[alias]` 改的是**最外层属性名**
     （`parts` 逆序累积）⇒ `np.random.seed` 的限定名被打成 `random.numpy`；
   - 族判定写成 `qual.split(".")[0] in {"random", "numpy.random"}` ⇒ 两段族名
     `numpy.random` 永远匹配不上一段切分 ⇒ `import numpy`（无别名）写法
     **一条 finding 都没有**（模块 docstring 明示 numpy.random 纳入检测）。
2. **探针快照定位把测试文件的行号用到目标代码上**（`src/agents/debugger.py`）
   - 探针文件 `{module}_probe.py` 的内容是**生成的测试代码**，其帧行号与
     `original_target_code`（目标模块全文）**不同源**；跨文件守卫用
     `startswith(target_module)` 又把 `calc_probe.py` 放行 ⇒ 定位到目标里
     无关的函数并把该指引注入修复提示（实测：目标 `add()` 在第 2 行、
     探针帧在测试文件第 6 行 ⇒ 定位到 `multiply()`）。
3. **执行器早退路径漏清实例级沙箱状态**（`src/agents/executor.py`）
   - `EARLY_RETURN` / `UNAVAILABLE` 早退分支在状态清理**之前** return ⇒
     `_kernel_sandbox_obs` 残留到下一次调用 ⇒ 该次调用即便根本没有沙箱，
     `sandbox_launch_failure` 启发式也会被陈旧 obs 触发，把 `error_info.type`
     从 `test_failure` 改写成 `kernel_sandbox_unavailable`（**污染失败归因**）。

零 LLM / 零网络 / 零真实子进程：全部用 mock 驱动。
"""

from __future__ import annotations

from unittest import mock

import pytest

# ─── 1. 确定性守卫：numpy.random 检出 ─────────────────────────────────────────


def _guard_findings(source: str) -> list[str]:
    """跑确定性守卫扫描，返回 finding 列表（开关强制开）。"""
    from src.agents import deterministic_guard as dg

    with mock.patch.object(dg, "deterministic_guard_enabled", return_value=True):
        report = dg.scan_test_file(source, filename="t.py")
    return [f.detail for f in report.findings]


class TestNumpyRandomDetection:
    def test_numpy_random_without_alias_is_detected(self) -> None:
        """`import numpy` + `numpy.random.seed(1)` 必须报 random_usage（此前完全漏检）。"""
        findings = _guard_findings("import numpy\nnumpy.random.seed(1)\n")
        assert findings, "import numpy 写法的 numpy.random 调用未被检出"
        assert any("numpy.random.seed" in f for f in findings), findings

    def test_numpy_random_alias_is_detected_with_real_qualname(self) -> None:
        """`import numpy as np` 的限定名必须展开成 `numpy.random.seed`（此前打成 `random.numpy`）。"""
        findings = _guard_findings("import numpy as np\nnp.random.seed(1)\n")
        assert findings, "别名写法的 numpy.random 调用未被检出"
        assert any("numpy.random.seed" in f for f in findings), findings
        assert not any("random.numpy" in f for f in findings), findings

    def test_numpy_rand_call_is_detected(self) -> None:
        findings = _guard_findings("import numpy as np\nnp.random.rand()\n")
        assert any("numpy.random.rand" in f for f in findings), findings

    def test_stdlib_random_is_detected(self) -> None:
        findings = _guard_findings("import random\nrandom.seed(0)\n")
        assert any("random.seed" in f for f in findings), findings

    def test_numpy_non_random_call_is_not_flagged(self) -> None:
        """`numpy.array` 不是随机数 ⇒ 不得误报（族判定按前缀而非顶层名）。"""
        findings = _guard_findings("import numpy as np\nnp.array([1, 2])\n")
        assert not any("随机数" in f for f in findings), findings

    def test_similar_prefix_is_not_flagged(self) -> None:
        """`randomness.foo` 不得被当成 `random.*`（族判定要求 `族名.` 前缀）。"""
        findings = _guard_findings("import randomness\nrandomness.foo()\n")
        assert not any("随机数" in f for f in findings), findings


# ─── 2. 探针快照定位：不得用测试文件的行号索引目标代码 ─────────────────────────


def _mk_debugger():
    from src.agents.debugger import DebuggerAgent

    dbg = DebuggerAgent()
    dbg.llm_client = mock.MagicMock()
    return dbg


class TestProbeSnapshotLocation:
    # 目标代码：add() 在第 2 行，multiply() 在第 6 行（复现探针给的最小样本）。
    _TARGET = "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"

    def test_probe_file_frame_is_not_used_to_locate_target(self) -> None:
        """探针文件（`{module}_probe.py`）的帧行号属于**测试文件** ⇒ 不得定位到目标函数。"""
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "test_add", "file": "/tmp/aitester_probe_x/calc_probe.py", "line": 6}]}
        out = dbg._locate_repair_focus_from_probe(self._TARGET, snap, "calc")
        assert out["focused"] is False, f"探针文件帧被当成了目标帧：{out}"
        assert out["function_name"] is None

    def test_target_file_frame_still_locates(self) -> None:
        """目标模块自己的文件的帧仍照常定位（修复不得把正路也堵死）。"""
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "add", "file": "/data/calc.py", "line": 2}]}
        out = dbg._locate_repair_focus_from_probe(self._TARGET, snap, "calc")
        assert out["focused"] is True, out
        assert out["function_name"] == "add"

    def test_probe_file_frame_without_module_name_is_not_used(self) -> None:
        """target_module 缺席时探针文件帧同样不得定位（无从验证帧的归属）。"""
        dbg = _mk_debugger()
        snap = {"frames": [{"function": "test_add", "file": "/tmp/x/probe_probe.py", "line": 6}]}
        out = dbg._locate_repair_focus_from_probe(self._TARGET, snap, None)
        assert out["focused"] is False, out


# ─── 3. 执行器：早退路径必须清实例级沙箱状态 ─────────────────────────────────


class _FakeResult:
    returncode = 1
    stdout = ""
    stderr = "sandbox-exec: sandbox_apply: failed to apply profile"


class TestExecutorSandboxStateCleanup:
    def test_early_return_clears_instance_sandbox_state(self) -> None:
        """早退（EARLY_RETURN）后实例级 `_kernel_sandbox_obs` 不得残留。"""
        from src.agents import executor as ex
        from src.agents import kernel_sandbox as ks

        agent = ex.ExecutorAgent(timeout=30, use_docker=False, use_venv=False)
        with (
            mock.patch.object(ks, "kernel_sandbox_enabled", return_value=True),
            mock.patch.object(
                ks,
                "build_sandbox_command",
                return_value=(
                    ["sandbox-exec", "-p", "p", "python", "-m", "pytest"],
                    {"supported": True, "platform": "darwin", "backend": "seatbelt"},
                ),
            ),
            mock.patch.object(
                agent,
                "_run_pytest_with_retry",
                return_value=("x", ("EARLY_RETURN", {"type": "execution_dependency_missing"})),
            ),
            mock.patch.object(agent, "_auto_fix_imports", return_value="x"),
        ):
            agent._execute_local("code", "/tmp/x.py")
        assert agent._kernel_sandbox_obs == {}, f"实例级沙箱观测状态残留：{agent._kernel_sandbox_obs}"
        assert agent._kernel_sandbox_executable is None

    def test_next_call_error_attribution_is_not_polluted(self) -> None:
        """第二次调用（本次没有沙箱）的失败归因不得被上一次残留的 obs 改写。"""
        from src.agents import executor as ex
        from src.agents import kernel_sandbox as ks

        agent = ex.ExecutorAgent(timeout=30, use_docker=False, use_venv=False)
        with (
            mock.patch.object(ks, "kernel_sandbox_enabled", return_value=True),
            mock.patch.object(
                ks,
                "build_sandbox_command",
                return_value=(
                    ["sandbox-exec", "-p", "p", "python", "-m", "pytest"],
                    {"supported": True, "platform": "darwin", "backend": "seatbelt"},
                ),
            ),
            mock.patch.object(
                agent,
                "_run_pytest_with_retry",
                return_value=("x", ("EARLY_RETURN", {"type": "execution_dependency_missing"})),
            ),
            mock.patch.object(agent, "_auto_fix_imports", return_value="x"),
        ):
            agent._execute_local("code", "/tmp/x.py")

        with (
            mock.patch.object(ks, "kernel_sandbox_enabled", return_value=False),
            mock.patch.object(
                agent,
                "_run_pytest_with_retry",
                return_value=("sandbox-exec: sandbox_apply: failed", _FakeResult()),
            ),
            mock.patch.object(agent, "_auto_fix_imports", return_value="x"),
        ):
            result = agent._execute_local("code", "/tmp/x.py")

        assert "kernel_sandbox_obs" not in result, f"本次没有沙箱却带出观测层：{result.get('kernel_sandbox_obs')}"
        assert result["error_info"]["type"] == "test_failure", f"失败归因被陈旧 obs 改写：{result['error_info']}"


@pytest.mark.parametrize("path", ["early_return", "unavailable"])
def test_both_early_return_modes_clear_state(path: str) -> None:
    """EARLY_RETURN 与 UNAVAILABLE 两条早退路径都必须清状态。"""
    from src.agents import executor as ex
    from src.agents import kernel_sandbox as ks

    agent = ex.ExecutorAgent(timeout=30, use_docker=False, use_venv=False)
    payload = (
        ("EARLY_RETURN", {"type": "execution_dependency_missing"})
        if path == "early_return"
        else (
            "UNAVAILABLE",
            {"type": "execution_dependency_missing"},
        )
    )
    with (
        mock.patch.object(ks, "kernel_sandbox_enabled", return_value=True),
        mock.patch.object(
            ks,
            "build_sandbox_command",
            return_value=(
                ["sandbox-exec", "-p", "p", "python", "-m", "pytest"],
                {"supported": True, "platform": "darwin", "backend": "seatbelt"},
            ),
        ),
        mock.patch.object(agent, "_run_pytest_with_retry", return_value=("x", payload)),
        mock.patch.object(agent, "_auto_fix_imports", return_value="x"),
    ):
        agent._execute_local("code", "/tmp/x.py")
    assert agent._kernel_sandbox_obs == {}, f"{path} 路径残留了实例级沙箱状态"
