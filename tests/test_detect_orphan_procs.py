#!/usr/bin/env python3
"""孤儿嵌套测试子进程巡检器的回归锁定（K 轮 2026-10-17，零 LLM）。

锁定四件事：
1. **识别口径是四条件交集**——沙箱标记 + pytest 调用 + PPID==1 + 龄期阈值：
   任一条件缺失都不得判为泄漏（误杀合法长跑批次的代价远高于漏报）；
2. **ps 不可用 ≠ 无泄漏**——报告必须区分 `available=false` 与"扫描后零命中"，
   不得把"读不到进程表"静默判绿（与 G1/G2 门禁 fail-closed 纪律同构）；
3. **PS 解析容错**——头部/空行/截断行不得让巡检崩溃；etime 三种形态可解析；
4. **清理顺序与语义**——先 SIGTERM、宽限期后对仍存活者 SIGKILL；
   进程已自行退出时如实记录，不虚报"已杀"。

背景与诱因见 `scripts/tools/detect_orphan_procs.py` 模块 docstring
（实测两个 PPID=1 的变异体 pytest 进程各空转 ~7 小时）。
"""

from __future__ import annotations

import importlib.util
import json
import signal
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "tools" / "detect_orphan_procs.py"
_spec = importlib.util.spec_from_file_location("_detect_orphan_procs", _SCRIPT_PATH)
assert _spec and _spec.loader
detect = importlib.util.module_from_spec(_spec)
sys.modules["_detect_orphan_procs"] = detect
_spec.loader.exec_module(detect)

#: 真实 ps 行样例：pid / ppid / etime / command（command 含空格）
_LEAKED_CMD = "python -m pytest /var/folders/pj/tmpu8nw4j1j/test_mutant.py --tb=no -q"


def _proc(pid: int, ppid: int, etime: str, command: str) -> dict[str, Any]:
    return {
        "pid": pid,
        "ppid": ppid,
        "etime": etime,
        "age_seconds": detect.parse_etime(etime),
        "command": command,
    }


class TestParseEtime:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("05:30", 330),
            ("00:07", 7),
            ("01:02:03", 3723),
            ("7-04:12:33", 7 * 86400 + 4 * 3600 + 12 * 60 + 33),
            ("0-00:00:01", 1),
        ],
    )
    def test_known_formats(self, raw: str, expected: int) -> None:
        assert detect.parse_etime(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "12", "1:2:3:4", "1-2-3", "--:--"])
    def test_malformed_returns_none_not_guess(self, raw: str) -> None:
        """无法解析时返回 None（调用方按"龄期未知"跳过），不得猜一个数。"""
        assert detect.parse_etime(raw) is None


class TestParsePsOutput:
    def test_parses_rows_and_skips_noise(self) -> None:
        stdout = (
            "  PID  PPID ELAPSED COMMAND\n"  # 带 header 的容错（真实 -axo 无 header，这里锁容错）
            "\n"
            f"69946     1 07:04:26 {_LEAKED_CMD}\n"
            "  123   456   00:01 python script.py --flag value\n"
            "garbage line without numbers\n"
        )
        rows = detect.parse_ps_output(stdout)
        assert len(rows) == 2
        assert rows[0]["pid"] == 69946 and rows[0]["ppid"] == 1
        assert rows[0]["age_seconds"] == 7 * 3600 + 4 * 60 + 26
        assert rows[0]["command"].endswith("test_mutant.py --tb=no -q")
        assert rows[1]["command"] == "python script.py --flag value"

    def test_command_with_internal_multiple_spaces_preserved(self) -> None:
        rows = detect.parse_ps_output("  1   2   00:10   python -m pytest   /tmp/x/test_mutant.py\n")
        assert rows[0]["command"] == "python -m pytest   /tmp/x/test_mutant.py"


class TestClassifyLeaks:
    def test_four_condition_hit(self) -> None:
        leaked = detect.classify_leaks([_proc(69946, 1, "07:04:26", _LEAKED_CMD)], min_age_seconds=600)
        assert len(leaked) == 1
        assert leaked[0]["matched_marker"] == "test_mutant.py"
        assert leaked[0]["pid"] == 69946

    @pytest.mark.parametrize(
        ("ppid", "etime", "command", "reason"),
        [
            (4321, "07:04:26", _LEAKED_CMD, "ppid 非 1（正常在跑，不误杀）"),
            (1, "00:00:30", _LEAKED_CMD, "龄期低于阈值（正常嵌套 pytest）"),
            (1, "07:04:26", "python script.py --flag", "非 pytest 调用"),
            (1, "07:04:26", "python -m experiments.run_benchmark --dataset quixbugs", "无沙箱标记（合法长跑批次）"),
        ],
    )
    def test_missing_any_condition_never_flagged(self, ppid: int, etime: str, command: str, reason: str) -> None:
        assert detect.classify_leaks([_proc(1, ppid, etime, command)], min_age_seconds=600) == [], reason

    def test_unknown_age_is_skipped_not_flagged(self) -> None:
        """etime 解析失败 → age=None → 跳过（宁可漏报，不臆测龄期）。"""
        proc = {"pid": 1, "ppid": 1, "etime": "??", "age_seconds": None, "command": _LEAKED_CMD}
        assert detect.classify_leaks([proc], min_age_seconds=10) == []

    def test_all_sandbox_markers_recognized(self) -> None:
        for marker in detect.NESTED_TEST_MARKERS:
            command = f"python -m pytest /var/folders/tmp/{marker}/test_x.py -q"
            leaked = detect.classify_leaks([_proc(1, 1, "01:00:00", command)], min_age_seconds=600)
            assert len(leaked) == 1, f"标记未被识别：{marker}"

    def test_matched_marker_reported_for_manual_review(self) -> None:
        command = "python -m pytest /tmp/aitester_m1_add/x/test_add.py -q"
        leaked = detect.classify_leaks([_proc(7, 1, "00:20:00", command)], min_age_seconds=600)
        assert leaked[0]["matched_marker"] == "aitester_m1_"


class TestTerminatePids:
    def test_sigterm_then_sigkill_for_survivor(self) -> None:
        calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            calls.append((pid, sig))
            # 0 号信号 = 存活探测：让探测成功 → 走 SIGKILL 兜底

        results = detect.terminate_pids([42], grace_seconds=0, kill_fn=fake_kill, sleep_fn=lambda _s: None)
        assert results == [{"pid": 42, "sigterm": True, "sigkill": True}]
        assert calls == [(42, signal.SIGTERM), (42, 0), (42, signal.SIGKILL)]

    def test_process_gone_before_sigterm_is_recorded_not_claimed(self) -> None:
        def fake_kill(pid: int, sig: int) -> None:
            raise ProcessLookupError

        results = detect.terminate_pids([7], grace_seconds=0, kill_fn=fake_kill, sleep_fn=lambda _s: None)
        assert results == [{"pid": 7, "sigterm": False, "sigkill": False}]

    def test_process_gone_after_sigterm_skips_sigkill(self) -> None:
        calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            calls.append((pid, sig))
            if sig == 0:  # 探测时已退出
                raise ProcessLookupError

        results = detect.terminate_pids([9], grace_seconds=0, kill_fn=fake_kill, sleep_fn=lambda _s: None)
        assert results == [{"pid": 9, "sigterm": True, "sigkill": False}]
        assert (9, signal.SIGKILL) not in calls

    def test_grace_sleep_injected_and_ordered_by_input(self) -> None:
        slept: list[float] = []
        detect.terminate_pids(
            [3, 1, 2],
            grace_seconds=1.5,
            kill_fn=lambda _pid, _sig: None,
            sleep_fn=lambda seconds: slept.append(seconds),
        )
        assert slept == [1.5]


class TestMainCli:
    def test_no_leak_exit_zero(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(detect, "list_processes", lambda timeout=10.0: [_proc(5, 1, "00:01", "python x.py")])
        assert detect.main([]) == 0
        assert "[OK]" in capsys.readouterr().out

    def test_leak_exit_one_and_message(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(detect, "list_processes", lambda timeout=10.0: [_proc(69946, 1, "07:04:26", _LEAKED_CMD)])
        assert detect.main([]) == 1
        out = capsys.readouterr().out
        assert "[LEAK]" in out and "69946" in out and "--kill" in out

    def test_json_mode_schema(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(detect, "list_processes", lambda timeout=10.0: [_proc(69946, 1, "07:04:26", _LEAKED_CMD)])
        assert detect.main(["--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["available"] is True
        assert payload["scanned"] == 1
        assert payload["leaked_count"] == 1
        assert payload["leaked"][0]["matched_marker"] == "test_mutant.py"

    def test_ps_unavailable_is_not_silent_green(self, monkeypatch, capsys) -> None:
        """ps 不可用：提示明确区分于"零命中"，且不阻断（沙箱已知限制）。"""

        def boom(timeout: float = 10.0) -> list[dict[str, Any]]:
            raise RuntimeError("ps 被沙箱禁止")

        monkeypatch.setattr(detect, "list_processes", boom)
        assert detect.main([]) == 0
        out = capsys.readouterr().out
        assert "[SKIP]" in out and "ps 被沙箱禁止" in out

    def test_ps_unavailable_json_marks_available_false(self, monkeypatch, capsys) -> None:
        def boom(timeout: float = 10.0) -> list[dict[str, Any]]:
            raise RuntimeError("ps 被沙箱禁止")

        monkeypatch.setattr(detect, "list_processes", boom)
        assert detect.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["available"] is False and payload["leaked"] == []

    def test_kill_mode_recovered_exit_zero(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(detect, "list_processes", lambda timeout=10.0: [_proc(69946, 1, "07:04:26", _LEAKED_CMD)])
        monkeypatch.setattr(
            detect,
            "terminate_pids",
            lambda pids, **kwargs: [{"pid": pid, "sigterm": True, "sigkill": True} for pid in pids],
        )
        assert detect.main(["--kill"]) == 0
        out = capsys.readouterr().out
        assert "已处理 pid=69946" in out

    def test_kill_mode_unrecovered_exit_one(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(detect, "list_processes", lambda timeout=10.0: [_proc(69946, 1, "07:04:26", _LEAKED_CMD)])
        monkeypatch.setattr(
            detect,
            "terminate_pids",
            lambda pids, **kwargs: [{"pid": pid, "sigterm": False, "sigkill": False} for pid in pids],
        )
        assert detect.main(["--kill"]) == 1
        assert "未回收" in capsys.readouterr().out
