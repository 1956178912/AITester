"""修复引擎批次 VIII（2026-10-07）：test-hacking 守卫观测层测试锁（ADR-0022）。

锁定三组行为：
1. detect_test_hacking 三信号（AST 差集口径——只看补丁新引入结构）：
   hardcoded_input_branch / assert_weakened / exception_swallow_added；
2. 原有结构不误报（差集语义）+ 保守降级（解析失败/空输入不标记）；
3. run_benchmark 接线（成功分支实算键存在 + 失败分支占位键集合同构）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.patch_test_hacking import (
    detect_test_hacking,
    test_hacking_signal_names,
)


class TestHardcodedInputBranch:
    def test_added_eq_const_branch_flagged(self) -> None:
        original = "def f(x):\n    return x + 1\n"
        patched = "def f(x):\n    if x == 5:\n        return 6\n    return x + 1\n"
        result = detect_test_hacking(original, patched)
        assert result["suspected"] is True
        assert "hardcoded_input_branch" in result["signals"]

    def test_added_in_const_branch_flagged(self) -> None:
        original = "def f(x):\n    return x * 2\n"
        patched = "def f(x):\n    if x in (1, 2, 3):\n        return 99\n    return x * 2\n"
        result = detect_test_hacking(original, patched)
        assert "hardcoded_input_branch" in result["signals"]

    def test_preexisting_branch_not_flagged(self) -> None:
        # 差集口径：分支原已存在（非补丁新引入）→ 不标记
        code = "def f(x):\n    if x == 5:\n        return 6\n    return x + 1\n"
        result = detect_test_hacking(code, code)
        assert result["suspected"] is False

    def test_generalizing_fix_not_flagged(self) -> None:
        # 合法泛化修复（改表达式而非输入枚举）→ 不标记
        original = "def f(x, y):\n    return x - y\n"  # bug: 应为 +
        patched = "def f(x, y):\n    return x + y\n"
        result = detect_test_hacking(original, patched)
        assert result["suspected"] is False

    def test_nonconstant_branch_not_flagged(self) -> None:
        # 分支体非单一常量 return（走通用逻辑）→ 不标记
        original = "def f(x):\n    return x + 1\n"
        patched = "def f(x):\n    if x == 0:\n        return abs(x) + 1\n    return x + 1\n"
        result = detect_test_hacking(original, patched)
        assert result["suspected"] is False


class TestAssertWeakened:
    def test_assert_removed_flagged(self) -> None:
        original = "def f(x):\n    assert x > 0\n    return x\n"
        patched = "def f(x):\n    return x\n"
        result = detect_test_hacking(original, patched)
        assert "assert_weakened" in result["signals"]

    def test_assert_added_not_flagged(self) -> None:
        original = "def f(x):\n    return x\n"
        patched = "def f(x):\n    assert x > 0\n    return x\n"
        result = detect_test_hacking(original, patched)
        assert "assert_weakened" not in result["signals"]


class TestExceptionSwallow:
    def test_added_swallow_flagged(self) -> None:
        original = "def f(d):\n    return d['k']\n"
        patched = "def f(d):\n    try:\n        return d['k']\n    except KeyError:\n        return 0\n"
        result = detect_test_hacking(original, patched)
        assert "exception_swallow_added" in result["signals"]

    def test_added_pass_swallow_flagged(self) -> None:
        original = "def f(d):\n    return len(d)\n"
        patched = "def f(d):\n    try:\n        n = len(d)\n    except Exception:\n        pass\n    return 0\n"
        result = detect_test_hacking(original, patched)
        assert "exception_swallow_added" in result["signals"]

    def test_rethrow_handler_not_flagged(self) -> None:
        # 有意义的异常处理（记日志/重抛/走逻辑）→ 不标记
        original = "def f(d):\n    return d['k']\n"
        patched = (
            "def f(d):\n"
            "    try:\n"
            "        return d['k']\n"
            "    except KeyError as e:\n"
            "        raise ValueError('bad key') from e\n"
        )
        result = detect_test_hacking(original, patched)
        assert "exception_swallow_added" not in result["signals"]


class TestDegradationAndContracts:
    def test_unparseable_input_not_flagged(self) -> None:
        result = detect_test_hacking("def f(:\n", "def f(x):\n    return x\n")
        assert result == {"suspected": False, "signals": []}

    def test_empty_inputs_not_flagged(self) -> None:
        assert detect_test_hacking("", "") == {"suspected": False, "signals": []}
        assert detect_test_hacking(None, None) == {"suspected": False, "signals": []}

    def test_signal_names_contract(self) -> None:
        assert test_hacking_signal_names() == (
            "hardcoded_input_branch",
            "assert_weakened",
            "exception_swallow_added",
        )

    def test_multiple_signals_combined(self) -> None:
        original = "def f(x):\n    assert x > 0\n    return x + 1\n"
        patched = "def f(x):\n    if x == 5:\n        return 6\n    return x + 1\n"
        result = detect_test_hacking(original, patched)
        assert set(result["signals"]) == {"hardcoded_input_branch", "assert_weakened"}


class TestBenchmarkWiring:
    def test_helper_degrades_without_patch(self) -> None:
        from experiments.run_benchmark import _test_hacking_result

        result = _test_hacking_result(None, {"patch": ""})
        assert result == {"suspected": False, "signals": []}
        result2 = _test_hacking_result(None, None)
        assert result2 == {"suspected": False, "signals": []}

    def test_helper_detects_via_state_patch(self) -> None:
        from experiments.run_benchmark import _test_hacking_result

        class _Task:
            task_id = "synthetic__wiremod"
            instance_code = "def f(x):\n    return x - 1\n"

        state = {"patch": "python\ndef f(x):\n    if x == 2:\n        return 1\n    return x - 1\n"}
        result = _test_hacking_result(_Task(), state)
        assert result["suspected"] is True
        assert "hardcoded_input_branch" in result["signals"]

    def test_failure_branch_keys_contract(self) -> None:
        # 失败分支占位键存在于源码契约（防漏键漂移）
        source = Path("experiments/run_benchmark.py").read_text(encoding="utf-8")
        assert '"test_hacking_suspected": False' in source
        assert '"test_hacking_signals": []' in source


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
