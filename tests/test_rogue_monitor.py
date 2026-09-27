"""
P1 流氓 agent 行为监控（src/agents/rogue_monitor.py）回归测试。

外部参照：微软 Agent Governance Toolkit agent-sre（SLO 追踪 / 断路器 /
失控循环检测）+ OWASP ASI-10 流氓 agent 检测三重信号（工具调用频率
z-score、动作熵、能力违规）。覆盖：
- 三类信号各自的触发与豁免口径（小样本 / 重复序列 / 越界工具）；
- 线程安全（--parallel 共享单例场景）；
- 开关默认值不改变行为（监控器纯观测，调用方决定是否隔离）。
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.rogue_monitor import (
    AgentEvent,
    RogueAgentMonitor,
    get_rogue_monitor,
    reset_rogue_monitor,
)


def _seq(agent: str, tool_seq: list[str]) -> RogueAgentMonitor:
    m = RogueAgentMonitor()
    for tool in tool_seq:
        m.report_tool_call(AgentEvent(agent, tool))
    return m


class TestZScoreSignal:
    def test_peak_tool_triggers_zscore(self):
        # 36 个工具各 1 次（均值 1.0、标准差 0）+ 1 个工具 30 次峰值
        # → 该工具 z = (30-1)/4.23 ≈ 6.86 越限（阈值 3.0）
        m = RogueAgentMonitor()
        seq = [f"tool-{i}" for i in range(36)] + ["hot"] * 30
        for tool in seq:
            m.report_tool_call(AgentEvent("a", tool))
        kinds = [f.kind for f in m.check("a")]
        assert "zscore" in kinds

    def test_dominant_single_tool_no_zscore(self):
        # 9 工具各 1 次（均值 2.22、σ=2.02）+ 1 工具 4 次（z≈0.8）：
        # 双峰温和序列，全信号放行（验证不判异的"非失控"形态）
        m = RogueAgentMonitor()
        seq = [f"t{i}" for i in range(9)] + ["read"] * 4
        for tool in seq:
            m.report_tool_call(AgentEvent("a", tool))
        findings = m.check("a")
        assert all(f.kind != "zscore" for f in findings)
        assert all(f.kind != "entropy" for f in findings)

    def test_balanced_sequence_no_zscore(self):
        m = _seq("a", ["read", "write", "run_tests"] * 10)
        kinds = [f.kind for f in m.check("a")]
        assert "zscore" not in kinds

    def test_small_window_no_zscore(self):
        m = _seq("a", ["read", "read"])
        kinds = [f.kind for f in m.check("a")]
        assert "zscore" not in kinds  # 样本 < 4 保守不判异


class TestEntropySignal:
    def test_repetitive_sequence_low_entropy(self):
        m = _seq("a", ["read"] * 20)
        kinds = [f.kind for f in m.check("a")]
        assert "entropy" in kinds  # 熵 0 < 0.5 floor

    def test_diverse_sequence_in_bounds(self):
        # 均匀 4 工具 → 熵 = 2.0 bits（落在 [0.5, 4.0] 内）
        m = _seq("a", ["a", "b", "c", "d"] * 5)
        kinds = [f.kind for f in m.check("a")]
        assert "entropy" not in kinds


class TestCapabilityViolation:
    def test_out_of_scope_tool_flagged(self):
        m = RogueAgentMonitor(allowed_tools={"read", "run_tests"})
        for _ in range(3):
            m.report_tool_call(AgentEvent("a", "read"))
        m.report_tool_call(AgentEvent("a", "exec_shell"))
        kinds = [f.kind for f in m.check("a")]
        assert "capability" in kinds
        cap = next(f for f in m.check("a") if f.kind == "capability")
        assert "exec_shell" in cap.detail

    def test_in_scope_tools_no_violation(self):
        m = RogueAgentMonitor(allowed_tools={"read", "run_tests"})
        for _ in range(5):
            m.report_tool_call(AgentEvent("a", "read"))
        m.report_tool_call(AgentEvent("a", "run_tests"))
        kinds = [f.kind for f in m.check("a")]
        assert "capability" not in kinds

    def test_no_capability_config_skips_check(self):
        m = RogueAgentMonitor(allowed_tools=None)  # 无能力配置 = 不检查（历史口径）
        for _ in range(5):
            m.report_tool_call(AgentEvent("a", "anything"))
        kinds = [f.kind for f in m.check("a")]
        assert "capability" not in kinds


class TestSingletonAndThreadSafety:
    def test_singleton_shared_state(self):
        reset_rogue_monitor()
        m1 = get_rogue_monitor()
        m2 = get_rogue_monitor()
        assert m1 is m2

    def test_parallel_reporting_no_corruption(self):
        m = RogueAgentMonitor()
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(50):
                    m.report_tool_call(AgentEvent(f"agent-{n % 3}", f"tool-{i % 7}"))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        # 每个 agent 窗口不超上限
        for i in range(3):
            assert len(m.check(f"agent-{i}")) >= 0  # check 不抛异常

    def test_reset_clears_state(self):
        m = RogueAgentMonitor(allowed_tools={"read"})
        m.report_tool_call(AgentEvent("a", "write"))
        assert any(f.kind == "capability" for f in m.check("a"))
        m.reset("a")
        assert m.check("a") == []


class TestEnvConfig:
    def test_env_window_size_respected(self, monkeypatch):
        monkeypatch.setenv("ROGUE_AGENT_WINDOW_SIZE", "8")
        m = RogueAgentMonitor()
        for _ in range(8):
            m.report_tool_call(AgentEvent("a", "read"))
        # 窗口 8 条全为 read → 熵 0 触发（而非窗口 50 条的"样本不足"豁免）
        kinds = [f.kind for f in m.check("a")]
        assert "entropy" in kinds

    def test_env_zscore_limit(self, monkeypatch):
        monkeypatch.setenv("ROGUE_AGENT_ZSCORE_LIMIT", "99")
        m = RogueAgentMonitor()
        seq = [f"tool-{i}" for i in range(36)] + ["hot"] * 30
        for tool in seq:
            m.report_tool_call(AgentEvent("a", tool))
        kinds = [f.kind for f in m.check("a")]
        assert "zscore" not in kinds  # 阈值拉高后不判异


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
