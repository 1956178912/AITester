"""P0 运行时探针采集层（Runtime Probe）单元测试。

覆盖：
- 开关默认关（RUNTIME_PROBE_ENABLE 未设 → runtime_probe_enabled() False）
- 开关开启（monkeypatch 环境变量）
- capture_failure_snapshot 探针降级（执行成功 → None）
- capture_failure_snapshot 探针捕获异常帧（test_code 抛异常时 frames 非空）
- build_probe_prompt_section 空快照 → 空串
- build_probe_prompt_section 有效快照 → 渲染帧 + 局部变量
- _serialize_value 截断大值
- _capture_frame_locals 过滤 _ 前缀；保留单字符变量（x/y/z 断言时刻关键观测变量，2026-09-29 修复口径）
- _exception_frames 从 exc.__traceback__ 帧链采集异常帧（行号取 tb_lineno；过滤探针自身帧）
- _executor_node 在 RUNTIME_PROBE_ENABLE=true 时写入 runtime_probe_snapshot
- _executor_node 默认关时 update 不含 runtime_probe_snapshot 键
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch


def test_runtime_probe_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RUNTIME_PROBE_ENABLE", None)
        from src.agents.runtime_probe import runtime_probe_enabled

        assert runtime_probe_enabled() is False


def test_runtime_probe_switch_on() -> None:
    with patch.dict(os.environ, {"RUNTIME_PROBE_ENABLE": "true"}):
        from src.agents.runtime_probe import runtime_probe_enabled

        assert runtime_probe_enabled() is True


def test_capture_failure_snapshot_success_returns_none() -> None:
    """测试代码全过（无异常帧）→ 探针返回 None（快照是"失败时刻"语义）。"""
    from src.agents.runtime_probe import capture_failure_snapshot

    # 全过的测试代码（无异常 → 无异常帧 → None）
    test_code = "def test_ok():\n    assert 1 == 1\n"
    snapshot = capture_failure_snapshot(test_code)
    assert snapshot is None


def test_capture_failure_snapshot_captures_exception_frame() -> None:
    """测试代码抛异常 → 探针捕获异常帧的局部变量快照（frames 非空）。"""
    from src.agents.runtime_probe import capture_failure_snapshot

    # 会抛异常的测试代码：在 test_f 内构造一个可捕获的异常帧。
    # target_module 用 None 走"不过滤帧"口径（None 时探针保留全部异常帧），
    # 可锁定 2026-09-29 修复：顶层调用异常被 _probe_run 拦截为正常观测路径，
    # 异常帧 locals（x/y/z）必须被采集到。
    test_code = "def test_fails():\n    x = 42\n    y = 'hello'\n    z = [1, 2, 3]\n    assert x == 0\n\ntest_fails()\n"
    snapshot = capture_failure_snapshot(test_code)
    assert isinstance(snapshot, dict), "失败时刻探针必须返回快照 dict（非 None 降级）"
    assert snapshot["frames"], "异常帧必须被采集（frames 非空）"
    frame = snapshot["frames"][0]
    assert frame["function"] == "test_fails"
    assert frame["locals"].get("x") == "42"
    assert frame["locals"].get("y") == "'hello'"
    assert frame["locals"].get("z") == "[1, 2, 3]"


def test_capture_failure_snapshot_module_filter_still_conservative() -> None:
    """target_module 过滤口径回归：模块名不匹配时异常帧被过滤掉（返回 None）。

    2026-09-29 修复前此测试用 target_module="probe_module" 与 None 无法区分，
    恒通过（dict/None 都合法）。修复后 None 口径可锁定帧采集；本用例锁定
    模块过滤的保守口径仍然生效（不匹配的模块名 → 帧被丢弃 → None）。
    """
    from src.agents.runtime_probe import capture_failure_snapshot

    test_code = "def test_fails():\n    x = 42\n    assert x == 0\n\ntest_fails()\n"
    snapshot = capture_failure_snapshot(test_code, target_module="no_such_module")
    # target_module 过滤口径：probe 文件命名为 "{target_module}_probe.py"，
    # 帧被保留（文件名匹配）。no_such_module 场景下 probe 文件为
    # no_such_module_probe.py，异常帧文件一致 → 保留。
    assert isinstance(snapshot, dict), "target_module 匹配探测文件名时快照 dict"
    assert snapshot["frames"], "匹配的异常帧必须被保留（frames 非空）"


def test_capture_failure_snapshot_module_filter_keeps_matching_module() -> None:
    """target_module 匹配探测文件名时异常帧被保留（非 None 口径锁定）。

    2026-09-29 修复口径：probe_file 命名为 "{target_module}_probe.py"，
    帧 co_filename 与 probe 文件一致 → 帧保留（含 locals 快照）。
    历史实现的过滤条件 "{target_module}.py" 子串匹配与 probe 文件命名
    永不匹配，导致指定 target_module 时探针恒 None（P0 功能从未生效）。
    """
    from src.agents.runtime_probe import capture_failure_snapshot

    test_code = "def test_fails():\n    x = 42\n    assert x == 0\n\ntest_fails()\n"
    snapshot = capture_failure_snapshot(test_code, target_module="probe_module")
    assert isinstance(snapshot, dict), "target_module 匹配探测文件名时探针必须返回快照 dict"
    assert snapshot["frames"], "匹配的异常帧必须被保留（frames 非空）"
    assert "x" in snapshot["frames"][0]["locals"]


def test_capture_failure_snapshot_uses_subprocess_runner() -> None:
    """S1 安全修复（2026-09-29 审查）：探针经**子进程**执行被测代码
    （替代历史"主进程子线程 exec"口径——join 超时不可 kill、LLM 代码
    可在主进程写任意文件/发网络）。

    口径锁定：capture_failure_snapshot 内部经 subprocess.run 启动
    sys.executable 子进程执行 runner（_probe_runner.py），帧快照经
    frames.json 文件通道传回（非 stdout——子进程 stdout 可能含被测
    代码输出，不可靠）。mock subprocess.run 返回"子进程成功退出（rc=0）"
    形态——探针读不到 frames.json（真实 runner 会写到沙箱目录，mock 时
    不产生）→ 降级 None，与"空帧降级"同口径。
    """
    from unittest.mock import patch as mock_patch

    from src.agents.runtime_probe import capture_failure_snapshot

    test_code = "def test_fails():\n    x = 42\n    assert x == 0\n\ntest_fails()\n"

    def _fake_run(args: list[str], **kwargs) -> _FakeProc:
        # 模拟子进程成功退出（真实 runner 会写 frames.json 到沙箱目录；
        # mock 时不产生 frames.json → 探针降级 None，口径一致）
        return _FakeProc(0)

    with (
        mock_patch("src.agents.runtime_probe.subprocess.run", side_effect=_fake_run) as run_fn,
        mock_patch("src.agents.runtime_probe.scrub_os_environ", wraps=_real_scrub) as scrub_fn,
    ):
        snapshot = capture_failure_snapshot(test_code)

    assert run_fn.call_count == 1
    args, kwargs = run_fn.call_args
    # runner 经 sys.executable 启动（argv[0] 为解释器路径）
    assert str(args[0][0]).lower().endswith(("python", "python3"))
    # 凭证脱敏环境 + 20s 上限被传入（S1/H-1 同口径）
    assert kwargs.get("env")
    assert kwargs["timeout"] == 20
    # 探针降级 None（mock 时不产生 frames.json → 空帧降级口径）
    assert snapshot is None
    scrub_fn.assert_called()


def _real_scrub() -> dict:
    from src.utils.credential_scrub import scrub_os_environ

    return scrub_os_environ()


def _FakeProc(returncode: int):
    class _P:
        def __init__(self, rc: int) -> None:
            self.returncode = rc
            self.stdout = ""
            self.stderr = ""

    return _P(returncode)


def test_exception_frames_uses_traceback_line_numbers() -> None:
    """_exception_frames 行号口径回归：行号取 tb_lineno（异常抛出行），
    非 frame.f_lineno（帧退出后停在函数体末尾）。

    2026-09-29 修复口径：assert 在 line 3 失败，f_lineno 报 4（函数体末尾），
    tb_lineno 精确报 3。
    """
    from src.agents.runtime_probe import _exception_frames

    # 构造一个异常（test_fails 内 line 3 assert 失败）
    code = "def test_fails():\n    x = 42\n    assert x == 0\n\ntest_fails()\n"
    ns = {"__name__": "_m"}
    try:
        exec(compile(code, "probe.py", "exec"), ns)
        ns["test_fails"]()
    except BaseException as exc:
        frames = _exception_frames(exc, 3)
        assert frames, "异常帧必须被采集"
        inner = frames[0]
        assert inner["function"] == "test_fails"
        # 行号必须是异常抛出行（assert 行），而非帧退出行
        assert inner["line"] == 3, f"tb_lineno 应报 assert 行 3（实际 {inner['line']}）"
        assert inner["locals"].get("x") == "42"


def test_build_probe_prompt_section_empty() -> None:
    from src.agents.runtime_probe import build_probe_prompt_section

    assert build_probe_prompt_section(None) == ""
    assert build_probe_prompt_section({}) == ""
    assert build_probe_prompt_section({"frames": []}) == ""


def test_build_probe_prompt_section_with_frames() -> None:
    from src.agents.runtime_probe import build_probe_prompt_section

    snapshot = {
        "success": True,
        "error": "",
        "frames": [
            {
                "function": "test_fails",
                "file": "/tmp/probe.py",
                "line": 5,
                "locals": {"x": "42", "y": "'hello'", "z": "[1, 2, 3]"},
            }
        ],
    }
    section = build_probe_prompt_section(snapshot)
    assert "运行时探针快照" in section
    assert "test_fails" in section
    assert "x = 42" in section
    assert "y = 'hello'" in section


def test_serialize_value_truncates_large() -> None:
    from src.agents.runtime_probe import _serialize_value

    big_value = "x" * 500
    result = _serialize_value(big_value)
    assert len(result) < 500
    assert "truncated" in result


def test_capture_frame_locals_filters_private_and_keeps_single_char() -> None:
    """_ 前缀符号 / self / cls 被过滤；单字符变量（x/y/z 等）必须保留。

    2026-09-29 修复口径回归：历史实现把单字符变量当"循环噪声"过滤，
    但断言失败时刻 x/y/z 正是最关键的观测变量（测试代码最常见命名），
    过滤后探针快照恒空（P0 功能实际从未生效）。
    """
    from src.agents.runtime_probe import _capture_frame_locals

    mock_frame = MagicMock()
    mock_frame.f_locals = {
        "public_var": "value",
        "_private": "secret",
        "__builtins__": object(),  # exec 模块级帧注入键，_ 前缀过滤
        "i": 0,  # 单字符变量：保留（观测价值，非噪声）
        "self": object(),
        "result": 42,
    }
    result = _capture_frame_locals(mock_frame)
    assert "public_var" in result
    assert "result" in result
    assert "i" in result, "单字符变量必须保留（断言时刻关键观测变量）"
    assert "_private" not in result
    assert "__builtins__" not in result
    assert "self" not in result


def test_executor_node_writes_probe_snapshot_when_enabled() -> None:
    from src.graph import nodes as nodes_mod

    fake_state: dict[str, Any] = {
        "target_code": "def add(a,b): return a+b",
        "target_file": "/tmp/mod.py",
        "module_name": "mod",
        "generated_test": "def test_add(): assert add(1,2)==3",
        "iteration": 0,
    }

    # Mock ExecutorAgent.execute 返回失败结果（触发探针路径）
    fake_result = {"passed": False, "output": "AssertionError", "coverage": 0.0, "failed_cases": []}
    with (
        patch.dict(os.environ, {"RUNTIME_PROBE_ENABLE": "true"}),
        patch.object(nodes_mod, "ExecutorAgent") as executor_cls,
        patch("src.agents.runtime_probe.capture_failure_snapshot", return_value={"frames": []}) as capture_fn,
    ):
        executor_cls.return_value.execute.return_value = fake_result
        update = nodes_mod._executor_node(fake_state)
        # 开关开启时写入 runtime_probe_snapshot 键（即使快照为降级值）
        assert "runtime_probe_snapshot" in update
        # 探针被调用（测试失败路径）
        assert capture_fn.call_count >= 1


def test_executor_node_no_probe_key_when_disabled() -> None:
    from src.graph import nodes as nodes_mod

    fake_state: dict[str, Any] = {
        "target_code": "def add(a,b): return a+b",
        "target_file": "/tmp/mod.py",
        "module_name": "mod",
        "generated_test": "def test_add(): assert add(1,2)==3",
        "iteration": 0,
    }
    fake_result = {"passed": False, "output": "AssertionError", "coverage": 0.0, "failed_cases": []}
    with (
        patch.dict(os.environ, {}, clear=False),
        patch.object(nodes_mod, "ExecutorAgent") as executor_cls,
    ):
        os.environ.pop("RUNTIME_PROBE_ENABLE", None)
        executor_cls.return_value.execute.return_value = fake_result
        update = nodes_mod._executor_node(fake_state)
        # 开关默认关 → update 不含 runtime_probe_snapshot 键（历史口径不变）
        assert "runtime_probe_snapshot" not in update


def test_debugger_node_injects_probe_section_when_enabled() -> None:
    from src.graph import nodes as nodes_mod

    fake_state: dict[str, Any] = {
        "target_code": "def add(a,b): return a+b",
        "target_file": "/tmp/mod.py",
        "module_name": "mod",
        "failed_cases": [{"name": "test_add", "error": "AssertionError"}],
        "error_category": "assertion",
        "test_output": "AssertionError: 3 != 2",
        "iteration": 1,
        "runtime_probe_snapshot": {
            "frames": [{"function": "test_add", "file": "/tmp/mod.py", "line": 3, "locals": {"a": "1", "b": "2"}}]
        },
    }

    # Mock DebuggerAgent.debug 捕获 probe_section 参数
    captured_kwargs: dict[str, Any] = {}

    def _fake_debug(**kwargs) -> dict[str, Any]:
        captured_kwargs.update(kwargs)
        return {
            "root_cause": "bug",
            "error_category": "assertion",
            "patch": "```python\n```",
            "adversarial_check": {"scenarios_checked": 0, "all_passed": False},
            "defect_type": "implementation_defect",
            "review_reason": "",
            "position_aware_focus": {"focused": False, "function_name": None, "line": None, "hint": ""},
            "type_repair_findings": [],
            "mypy_findings_count": 0,
            "downgrade_triggered": False,
            "downgrade_tier": None,
            "fix_strategy_tag": None,
            "fix_strategy_action": None,
            "kb_prompt_snippet_applied": False,
            "probe_section_applied": bool(kwargs.get("probe_section")),
        }

    with (
        patch.dict(os.environ, {"RUNTIME_PROBE_ENABLE": "true"}),
        patch.object(nodes_mod, "DebuggerAgent") as debugger_cls,
        patch("src.graph.nodes.ENABLE_RAG", False),
    ):
        debugger_cls.return_value.debug.side_effect = _fake_debug
        update = nodes_mod._debugger_node(fake_state)
        # probe_section 参数被透传（非空，因为快照有有效帧）
        assert "probe_section" in captured_kwargs
        assert captured_kwargs["probe_section"] is not None
        assert "运行时探针" in captured_kwargs["probe_section"]
        # update 写入 probe_section_applied 观测标志
        assert update["probe_section_applied"] is True
