"""graph/nodes 纯逻辑函数分支补齐（2026-10-02 批次·十一）。

锁定 nodes.py 未覆盖的纯逻辑 / mock 隔离分支（零真实 LLM / 零网络 / 零 git 子进程）：
- _is_within_allowed_roots：roots=None 默认白名单 / 显式 roots / realpath 归一化
- _write_file_atomic：成功原子替换 / 失败清理临时文件 + 抛异常
- _safe_write_patch：四道安全检查（未应用 / 空或过短 / 无函数定义 / 路径越权 /
  仓库核心黑名单 / 快照出参回填）
- _rollback_last_patch：快照缺失 / 目标缺失 / 成功回滚 / IO 异常
- _record_execution_trace / _append_trace_record：轨迹追加 + 覆盖率 delta 计算
- _patch_resample_enabled / _patch_resample_temperature / _patch_resample_max 开关
- _repo_core_protection_enabled 开关默认 + env 覆盖
- _planner_node 验证失败降级（mock PlannerAgent）
- logic_degraded 顶层抬升（G3：写侧 test_plan 内标记 ↔ 归因读侧顶层键路径对齐）
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ─── _is_within_allowed_roots 分支 ─────────────────────────────────────────


class TestIsWithinAllowedRootsBranches:
    def test_default_roots_tempdir_within(self):
        """默认白名单（_ALLOWED_WRITE_ROOTS）：系统临时目录内路径放行。"""
        from src.graph.nodes import _is_within_allowed_roots

        path = os.path.join(tempfile.gettempdir(), "sub", "file.py")
        assert _is_within_allowed_roots(path) is True

    def test_default_roots_repo_root_within(self):
        """仓库根目录内路径放行（_ALLOWED_WRITE_ROOTS[0] 为项目根）。"""
        from src.graph import nodes

        repo_root = nodes._ALLOWED_WRITE_ROOTS[0]
        path = os.path.join(repo_root, "data", "task_1", "target.py")
        assert nodes._is_within_allowed_roots(path) is True

    def test_explicit_roots_within(self):
        """显式 roots：路径在指定根内 → True。"""
        from src.graph.nodes import _is_within_allowed_roots

        custom_root = os.path.realpath(tempfile.gettempdir())
        path = os.path.join(custom_root, "mydir", "f.py")
        assert _is_within_allowed_roots(path, roots=(custom_root,)) is True

    def test_explicit_roots_outside(self):
        """显式 roots：路径不在指定根内 → False。"""
        from src.graph.nodes import _is_within_allowed_roots

        # 2026-10-18 CI 首跑实测：直接在系统临时目录旁建兄弟目录
        # （/tmp_backup）在 Linux/CI 上因根目录不可写而 PermissionError。
        # 改为在用户可写的私有父目录内构造 root/root_backup 兄弟前缀。
        base = tempfile.mkdtemp(prefix="aitester_roots_")
        custom_root = os.path.realpath(os.path.join(base, "root"))
        os.makedirs(custom_root)
        sibling = custom_root.rstrip(os.sep) + "_backup"
        try:
            path = os.path.join(sibling, "f.py")
            assert _is_within_allowed_roots(path, roots=(custom_root,)) is False
        finally:
            import shutil

            shutil.rmtree(base, ignore_errors=True)

    def test_root_itself_within(self):
        """路径即根目录本身 → True（含根目录自身口径）。"""
        from src.graph.nodes import _is_within_allowed_roots

        custom_root = os.path.realpath(tempfile.gettempdir())
        assert _is_within_allowed_roots(custom_root, roots=(custom_root,)) is True

    def test_symlink_normalized(self):
        """符号链接路径经 realpath 归一化后判定（macOS /var↔/private/var）。"""
        from src.graph import nodes

        custom_root = os.path.realpath(tempfile.gettempdir())
        # tempfile.gettempdir() 在 macOS 可能未含 /private 前缀，realpath 归一后一致
        abs_path = os.path.abspath(tempfile.gettempdir())
        # 无论 abspath 与 realpath 是否一致，realpath 口径下应在根内
        assert nodes._is_within_allowed_roots(abs_path, roots=(custom_root,)) is True


# ─── _write_file_atomic 分支 ───────────────────────────────────────────────


class TestWriteFileAtomicBranches:
    def test_success_replaces_content(self, tmp_path):
        from src.graph.nodes import _write_file_atomic

        target = tmp_path / "f.py"
        target.write_text("old")
        _write_file_atomic(str(target), "new")
        assert target.read_text() == "new"

    def test_success_no_temp_file_left(self, tmp_path):
        """原子写成功后无残留 .aitester_*.tmp 临时文件。"""
        from src.graph.nodes import _write_file_atomic

        target = tmp_path / "f.py"
        target.write_text("old")
        _write_file_atomic(str(target), "new")
        leftovers = [p for p in tmp_path.iterdir() if ".aitester_" in p.name and p.name.endswith(".tmp")]
        assert leftovers == []

    def test_failure_cleans_temp_and_raises(self, tmp_path):
        """写入异常（目标目录只读）→ 清理临时文件 + 抛出异常。"""
        import stat

        from src.graph.nodes import _write_file_atomic

        target = tmp_path / "f.py"
        target.write_text("old")
        # 让目标目录不可写（清空写权限）使 os.replace 失败
        original_mode = stat.S_IMODE(os.stat(tmp_path).st_mode)
        os.chmod(tmp_path, 0o555)  # r-x, 不可写
        try:
            with pytest.raises(OSError):
                _write_file_atomic(str(target), "new")
        finally:
            os.chmod(tmp_path, original_mode)
        # 临时文件已清理（目录内无 .aitester_*.tmp）
        leftovers = [p for p in tmp_path.iterdir() if ".aitester_" in p.name and p.name.endswith(".tmp")]
        assert leftovers == []


# ─── _safe_write_patch 四道安全检查 ────────────────────────────────────────


class TestSafeWritePatchBranches:
    def test_not_applied_returns_false(self, tmp_path, monkeypatch):
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")  # 关核心保护聚焦路径
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n")
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch("orig", "new_code", applied=False, state=state)
        assert out is False  # 补丁未生效 → 不写

    def test_same_code_returns_false(self, tmp_path, monkeypatch):
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n")
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch("def f():\n    return 1\n", "def f():\n    return 1\n", applied=True, state=state)
        assert out is False  # 新代码 == 原代码 → 不写

    def test_too_short_rejected(self, tmp_path, monkeypatch):
        """安全检查 1：新代码 < 原代码 10% → 拒绝。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n" * 20)  # 较长原代码
        original = target.read_text()
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch(original, "def f():\n    pass\n", applied=True, state=state)
        assert out is False

    def test_no_function_def_rejected(self, tmp_path, monkeypatch):
        """安全检查 2：新代码无 def → 拒绝。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n")
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch(target.read_text(), "x = 1\n", applied=True, state=state)
        assert out is False

    def test_path_outside_allowed_roots_rejected(self, tmp_path, monkeypatch):
        """安全检查 3：target_file 在白名单外 → 拒绝。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 构造白名单外的绝对路径（/root 之外的系统路径）
        state = {"target_file": "/nonexistent_root_xyz/f.py", "iteration": 0}
        out = _safe_write_patch("orig_code", "def f():\n    pass\n", applied=True, state=state)
        assert out is False

    def test_repo_core_path_rejected(self, tmp_path, monkeypatch):
        """安全检查 4：target_file 命中仓库核心（src/ 一级目录）→ 拒绝。"""
        import src.graph.nodes as nodes_mod

        monkeypatch.delenv("PATCH_PROTECT_REPO_CORE", raising=False)  # 默认开
        # 取仓库根（_ALLOWED_WRITE_ROOTS[0]），构造 src/core.py 核心路径
        repo_root = nodes_mod._ALLOWED_WRITE_ROOTS[0]
        core_path = os.path.join(repo_root, "src", "core_xyz_probe.py")
        state = {"target_file": core_path, "iteration": 0}
        out = nodes_mod._safe_write_patch("orig_code", "def f():\n    pass\n", applied=True, state=state)
        assert out is False  # src/ 一级目录命中核心保护

    def test_valid_write_returns_true_with_snapshot(self, tmp_path, monkeypatch):
        """全部检查通过 → 写盘成功 + snapshot_out 回填。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n" * 5)
        original = target.read_text()
        state = {"target_file": str(target), "iteration": 3}
        snap_out: dict = {}
        out = _safe_write_patch(original, "def f():\n    return 2\n", applied=True, state=state, snapshot_out=snap_out)
        assert out is True
        assert target.read_text() == "def f():\n    return 2\n"
        assert "path" in snap_out and snap_out["iteration"] == 3
        assert os.path.isfile(snap_out["path"])

    def test_snapshot_out_none_no_crash(self, tmp_path, monkeypatch):
        """snapshot_out=None（未传入）时写盘成功且不回填。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        target.write_text("def f():\n    return 1\n" * 5)
        original = target.read_text()
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch(original, "def f():\n    return 2\n", applied=True, state=state)
        assert out is True


# ─── _rollback_last_patch 分支 ─────────────────────────────────────────────


class TestRollbackLastPatchBranches:
    def test_no_snapshot_returns_false(self, tmp_path):
        from src.graph.nodes import _rollback_last_patch

        target = tmp_path / "f.py"
        target.write_text("patched_code\n")
        state = {"target_file": str(target), "_last_patch_snapshot": None}
        assert _rollback_last_patch(state) is False

    def test_missing_snapshot_file_returns_false(self, tmp_path):
        from src.graph.nodes import _rollback_last_patch

        target = tmp_path / "f.py"
        target.write_text("patched_code\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(tmp_path / "no_such_snap")}
        assert _rollback_last_patch(state) is False

    def test_no_target_file_returns_false(self, tmp_path):
        from src.graph.nodes import _rollback_last_patch

        snap = tmp_path / "snap"
        snap.write_text("original_code\n")
        state = {"target_file": "", "_last_patch_snapshot": str(snap)}
        assert _rollback_last_patch(state) is False

    def test_success_restores_and_cleans(self, tmp_path):
        """快照存在 + 目标存在 → 写回快照内容 + 删除快照 + 清理 state 键。"""
        from src.graph.nodes import _rollback_last_patch

        target = tmp_path / "f.py"
        target.write_text("bad_patched_code\n")
        snap = tmp_path / "snap"
        snap.write_text("original_code\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(snap), "_last_patch_iteration": 2}
        out = _rollback_last_patch(state)
        assert out is True
        assert target.read_text() == "original_code\n"
        assert not snap.exists()  # 快照已删除
        assert "_last_patch_snapshot" not in state  # state 键已清理
        assert "_last_patch_iteration" not in state

    def test_snapshot_read_failure_returns_false(self, tmp_path, monkeypatch):
        """快照文件读取异常（不可读）→ 保守返回 False（保留当前文件）。"""
        from src.graph import nodes

        target = tmp_path / "f.py"
        target.write_text("patched\n")
        snap = tmp_path / "snap"
        snap.write_text("original\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(snap)}
        # 让 open 读快照抛异常（精准：仅 mock open 返回的 read 抛异常，避免污染
        # 测试自身的 target.read_text）。直接 monkeypatch nodes._write_file_atomic
        # 使其抛异常，走 except 路径更聚焦。
        import builtins as _bi

        real_open = _bi.open

        def _fake_open(path, *args, **kwargs):
            # 仅对快照路径抛异常（target 文件读仍正常）
            if str(path) == str(snap):
                raise PermissionError("unreadable")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(_bi, "open", _fake_open)
        out = nodes._rollback_last_patch(state)
        assert out is False
        assert target.read_text().strip() == "patched"  # 当前文件未被污染


# ─── _record_execution_trace / _append_trace_record 分支 ──────────────────


class TestRecordExecutionTraceBranches:
    def test_first_round_no_prev_delta(self):
        from src.graph.nodes import _record_execution_trace

        state: dict = {"execution_trace": [], "iteration": 0}
        out = _record_execution_trace(state, passed=True, coverage=50.0, elapsed_seconds=2.0)
        assert len(out) == 1
        assert out[0]["coverage_delta"] is None  # 首轮无 delta
        assert out[0]["passed"] is True
        assert out[0]["coverage"] == 50.0

    def test_second_round_with_delta(self):
        from src.graph.nodes import _record_execution_trace

        state: dict = {"execution_trace": [{"coverage": 40.0}], "iteration": 1}
        out = _record_execution_trace(state, passed=False, coverage=55.0, elapsed_seconds=3.0)
        assert len(out) == 2
        assert out[1]["coverage_delta"] == 15.0  # 55 - 40

    def test_negative_delta(self):
        from src.graph.nodes import _record_execution_trace

        state: dict = {"execution_trace": [{"coverage": 80.0}], "iteration": 1}
        out = _record_execution_trace(state, passed=False, coverage=60.0, elapsed_seconds=1.0)
        assert out[1]["coverage_delta"] == -20.0

    def test_trace_none_treated_as_empty(self):
        """execution_trace 键缺失 / None → 视为首轮（delta=None）。"""
        from src.graph.nodes import _record_execution_trace

        state: dict = {"iteration": 0}
        out = _record_execution_trace(state, passed=True, coverage=10.0, elapsed_seconds=1.0)
        assert len(out) == 1
        assert out[0]["coverage_delta"] is None

    def test_reward_signals_present(self):
        from src.graph.nodes import _record_execution_trace

        state: dict = {"iteration": 0}
        out = _record_execution_trace(state, passed=True, coverage=10.0, elapsed_seconds=1.0)
        assert "reward_signals" in out[0]
        assert out[0]["reward_signals"]["correctness"] == 1.0

    def test_iteration_default_zero(self):
        from src.graph.nodes import _append_trace_record

        state: dict = {}
        out = _append_trace_record(state, [], passed=True, coverage=1.0, coverage_delta=None, elapsed_seconds=1.0)
        assert out[0]["iteration"] == 0


# ─── _patch_resample / 开关 env 解析 ──────────────────────────────────────


class TestPatchResampleSwitchBranches:
    def test_resample_enabled_default_false(self, monkeypatch):
        from src.graph.nodes import _patch_resample_enabled

        monkeypatch.delenv("PATCH_RESAMPLE_ENABLE", raising=False)
        assert _patch_resample_enabled() is False

    def test_resample_enabled_true(self, monkeypatch):
        from src.graph.nodes import _patch_resample_enabled

        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "true")
        assert _patch_resample_enabled() is True

    def test_resample_enabled_case_insensitive(self, monkeypatch):
        from src.graph.nodes import _patch_resample_enabled

        monkeypatch.setenv("PATCH_RESAMPLE_ENABLE", "TRUE")
        assert _patch_resample_enabled() is True

    def test_resample_max_default(self, monkeypatch):
        from src.graph.nodes import _patch_resample_max

        monkeypatch.delenv("PATCH_RESAMPLE_MAX", raising=False)
        assert _patch_resample_max() == 2

    def test_resample_max_clamped_to_zero(self, monkeypatch):
        from src.graph.nodes import _patch_resample_max

        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "-5")
        assert _patch_resample_max() == 0

    def test_resample_max_clamped_to_five(self, monkeypatch):
        from src.graph.nodes import _patch_resample_max

        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "99")
        assert _patch_resample_max() == 5

    def test_resample_max_invalid_value_falls_back(self, monkeypatch):
        from src.graph.nodes import _patch_resample_max

        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "not_a_number")
        assert _patch_resample_max() == 2  # ValueError → 默认 2

    def test_resample_temperature_returns_float(self, monkeypatch):
        """_patch_resample_temperature 读 patch_applier 档位温度（mock _current_context_tier）。"""
        from src.graph.nodes import _patch_resample_temperature

        with patch("src.tools.patch_applier._current_context_tier", return_value=("medium", 1, 0.2)):
            out = _patch_resample_temperature()
            assert out == 0.2

    def test_resample_temperature_import_failure_returns_none(self):
        """_current_context_tier 导入/调用失败 → None（沿用默认温度）。"""
        from src.graph.nodes import _patch_resample_temperature

        with patch("src.tools.patch_applier._current_context_tier", side_effect=ImportError("nope")):
            out = _patch_resample_temperature()
            assert out is None

    def test_repo_core_protection_default_true(self, monkeypatch):
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.delenv("PATCH_PROTECT_REPO_CORE", raising=False)
        assert _repo_core_protection_enabled() is True

    def test_repo_core_protection_zero_false(self, monkeypatch):
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        assert _repo_core_protection_enabled() is False

    def test_repo_core_protection_false_string_false(self, monkeypatch):
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "false")
        assert _repo_core_protection_enabled() is False

    def test_repo_core_protection_false_uppercase_false(self, monkeypatch):
        """大小写不敏感：'FALSE' 也应关闭（R3 修正确认）。"""
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "FALSE")
        assert _repo_core_protection_enabled() is False

    def test_repo_core_protection_one_true(self, monkeypatch):
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        assert _repo_core_protection_enabled() is True


# ─── _planner_node 验证失败降级（mock PlannerAgent）────────────────────────


class TestPlannerNodeFallbackBranches:
    def test_valid_plan_passthrough(self):
        """Planner 输出结构完整 → 直接采用（不降级）。"""
        from src.graph import nodes

        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"function_name": "f", "logic_analysis": {"input_domain": "int"}}
        state = {"target_code": "def f(x):\n    return x", "target_function": "f", "iteration": 0}
        with patch.object(nodes, "get_or_create_agent", return_value=mock_agent):
            out = nodes._planner_node(state)
        assert out["test_plan"]["function_name"] == "f"
        assert out["test_plan"].get("logic_degraded") is not True

    def test_invalid_plan_falls_back_to_default(self):
        """Planner 输出缺字段 → 降级到 _get_default_test_plan + logic_degraded。"""
        from src.graph import nodes

        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"function_name": "f"}  # 缺 logic_analysis
        state = {"target_code": "def f(x):\n    return x", "target_function": "f", "iteration": 0}
        with patch.object(nodes, "get_or_create_agent", return_value=mock_agent):
            out = nodes._planner_node(state)
        plan = out["test_plan"]
        assert plan["function_name"] == "f"
        assert plan.get("logic_degraded") is True  # 降级标记

    def test_plan_exception_falls_back_to_default(self):
        """Planner.plan 抛异常 → 兜底默认计划（不中断工作流）。"""
        from src.graph import nodes

        mock_agent = MagicMock()
        mock_agent.plan.side_effect = RuntimeError("LLM down")
        state = {"target_code": "def f(x):\n    return x", "target_function": "f", "iteration": 0}
        with patch.object(nodes, "get_or_create_agent", return_value=mock_agent):
            out = nodes._planner_node(state)
        assert "test_plan" in out
        # 异常路径仍产出可用计划（默认或降级）
        assert isinstance(out["test_plan"], dict)


# ─── G3（2026-10-16）：logic_degraded 顶层抬升（写侧↔读侧键路径对齐）────────


def _run_planner_with_mock(plan_return=None, plan_side_effect=None):
    """用 mock 的 PlannerAgent 跑一次 _planner_node，返回其 update dict。

    模块级（而非某个测试类的方法）：Planner 观测标记的顶层抬升现在有两条
    （logic_degraded / m10_leaf_fallback），两个测试类共用同一构造点。
    """
    from src.graph import nodes

    state = {"target_code": "def f(x):\n    return x", "target_function": "f", "iteration": 0}
    mock_agent = MagicMock()
    if plan_side_effect is not None:
        mock_agent.plan.side_effect = plan_side_effect
    else:
        mock_agent.plan.return_value = plan_return
    with patch.object(nodes, "get_or_create_agent", return_value=mock_agent):
        return nodes._planner_node(state)


class TestLogicDegradedTopLevelLift:
    """`logic_degraded` 必须同时出现在**状态顶层**，否则归因读侧恒 None。

    缺陷形态（G3）：三个写侧（_planner_node 两处降级分支 + PlannerAgent.plan 的
    M10 兜底/schema findings）都只写进 test_plan 内部，而唯一读侧
    `observability.failure_taxonomy.annotate_final_state` 读 `state.get("logic_degraded")`
    ——键既未声明也未抬升，"规约降级弱信号"分支从未 fire。既有单测手工构造
    顶层键（`{"logic_degraded": True}`）因此一直是绿的：测的是读侧纯函数，
    没有一条用例把写侧接上读侧。
    """

    def _run_planner(self, plan_return=None, plan_side_effect=None):
        return _run_planner_with_mock(plan_return, plan_side_effect)

    def test_declared_as_state_channel_with_false_default(self):
        from src.graph.state import AITesterState, create_initial_state

        assert "logic_degraded" in AITesterState.__annotations__, "未声明的键会被 LangGraph 丢弃"
        state = create_initial_state("u", "m.py", "x = 1\n", 3)
        assert state["logic_degraded"] is False

    def test_degraded_plan_lifts_flag_to_top_level(self):
        out = self._run_planner(plan_return={"function_name": "f"})  # 缺 logic_analysis → 降级
        assert out["test_plan"].get("logic_degraded") is True
        assert out["logic_degraded"] is True, "顶层未抬升 → 读侧 state.get() 恒 None"

    def test_llm_failure_path_lifts_flag_to_top_level(self):
        out = self._run_planner(plan_side_effect=RuntimeError("LLM down"))
        assert out["logic_degraded"] is True

    def test_valid_plan_lifts_explicit_false(self):
        """成功路径写显式 False（而非缺键）：False 本身是"逻辑驱动走通"的证据。"""
        out = self._run_planner(plan_return={"function_name": "f", "logic_analysis": {"input_domain": "int"}})
        assert out["logic_degraded"] is False

    def test_writer_output_reaches_taxonomy_reader(self):
        """端到端：写侧产物直接喂读侧 → 规约层失效桶（修复前落 UNCATEGORIZED）。"""
        from src.observability.failure_taxonomy import FailureBucket, annotate_final_state

        out = self._run_planner(plan_return={"function_name": "f"})
        final_state = {**out, "test_passed": False}  # 无 stop_reason：走 logic_degraded 弱信号
        annotation = annotate_final_state(final_state)
        assert annotation["bucket"] is FailureBucket.SPECIFICATION_FAILURE
        assert "logic_degraded" in annotation["detail"]

    def test_valid_plan_does_not_trigger_specification_failure(self):
        """反向锁：未降级时不得把任务误归入规约层失效桶（防"永远命中"）。"""
        from src.observability.failure_taxonomy import FailureBucket, annotate_final_state

        out = self._run_planner(plan_return={"function_name": "f", "logic_analysis": {"input_domain": "int"}})
        annotation = annotate_final_state({**out, "test_passed": False})
        assert annotation["bucket"] is FailureBucket.UNCATEGORIZED


class TestM10LeafFallbackTopLevelLift:
    """`m10_leaf_fallback` 必须抬到**状态顶层**，否则 ADR-0032 的可分离性不可机读。

    缺陷形态（I2，与 G3 的 logic_degraded 完全同构）：唯一写侧
    `PlannerAgent.plan` 的 M10 兜底分支把标记写进 `result["m10_leaf_fallback"]`
    ——即 test_plan **内部**；该键又从未在 AITesterState 声明，于是 LangGraph 直接
    丢弃、批次工件的投影行也读不到。ADR-0032 声称的
    "logic_degraded=True ∧ m10_leaf_fallback=True ⇒ 提取器误诊（非 LLM 真未输出）"
    因此无法从任何工件验证——正是登记册 §4 "只写不读（1 写侧、0 读侧）"条。
    """

    # PlannerAgent.plan 的 M10 兜底产物形状：logic_analysis 被填成空 dict，故
    # _validate_planner_output **通过**、planner 写的标记得以留在 test_plan 里。
    # 这与 G3 用例刻意缺 logic_analysis 触发**节点侧**默认计划降级（整份 plan
    # 被替换、planner 的标记随之丢弃）是两条不同路径，不可混用 fixture。
    def _m10_plan(self, leaf_fallback: bool) -> dict:
        plan = {
            "function_name": "f",
            "logic_analysis": {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            },
            "logic_degraded": True,
        }
        if leaf_fallback:
            plan["m10_leaf_fallback"] = True
        return plan

    def test_declared_as_state_channel_with_false_default(self):
        from src.graph.state import AITesterState, create_initial_state

        assert "m10_leaf_fallback" in AITesterState.__annotations__, "未声明的键会被 LangGraph 丢弃"
        assert create_initial_state("u", "m.py", "x = 1\n", 3)["m10_leaf_fallback"] is False

    def test_leaf_fallback_marker_lifts_to_top_level(self):
        out = _run_planner_with_mock(plan_return=self._m10_plan(leaf_fallback=True))
        assert out["test_plan"].get("m10_leaf_fallback") is True, "前提失效：写侧标记未留在 test_plan"
        assert out["m10_leaf_fallback"] is True, "顶层未抬升 → 通道/投影行读不到"

    def test_absent_marker_lifts_explicit_false(self):
        """无条件抬升：False 同样有意义——证明该次 M10 降级确为 LLM 真未输出。"""
        out = _run_planner_with_mock(plan_return=self._m10_plan(leaf_fallback=False))
        assert out["logic_degraded"] is True
        assert out["m10_leaf_fallback"] is False

    def test_valid_plan_lifts_explicit_false(self):
        out = _run_planner_with_mock(plan_return={"function_name": "f", "logic_analysis": {"input_domain": "int"}})
        assert out["m10_leaf_fallback"] is False

    def test_adr_0032_separability_is_machine_readable(self):
        """ADR-0032 核心主张：两个**顶层**标记的组合可区分两种 M10 降级成因。"""
        extractor_defect = _run_planner_with_mock(plan_return=self._m10_plan(leaf_fallback=True))
        genuine_m10 = _run_planner_with_mock(plan_return=self._m10_plan(leaf_fallback=False))
        assert (extractor_defect["logic_degraded"], extractor_defect["m10_leaf_fallback"]) == (True, True)
        assert (genuine_m10["logic_degraded"], genuine_m10["m10_leaf_fallback"]) == (True, False)

    def test_marker_survives_default_plan_replacement(self):
        """端到端（真 PlannerAgent + 真 _planner_node）：叶子回退场景下标记不得丢。

        这是 ADR-0032 最该生效、却恰好失效的路径：extract_json_object 的叶子
        降级档返回**最内层片段**（如 ``{"k": 42}``），片段通常连 function_name
        都没有 → `_validate_planner_output` 判 False → 节点用默认计划**整份替换**
        test_plan，planner 刚写下的 m10_leaf_fallback 随之被丢弃 → 顶层抬升只能
        读到 False，"提取器误诊"被记成"LLM 真未输出"（归因反向错误）。
        """
        from unittest.mock import patch as _patch

        from src.agents.planner import PlannerAgent
        from src.graph import nodes

        real = PlannerAgent()
        state = {"target_code": "def f(x):\n    return x", "target_function": "f", "iteration": 0}
        with (
            _patch.object(nodes, "get_or_create_agent", return_value=real),
            _patch.object(real, "_call_llm_with_cache", return_value='xx {"outer": stuff, {"k": 42}'),
        ):
            out = nodes._planner_node(state)
        assert out["logic_degraded"] is True
        assert out["m10_leaf_fallback"] is True, "默认计划替换吞掉了叶子回退标记"
