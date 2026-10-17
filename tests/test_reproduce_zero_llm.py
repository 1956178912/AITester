"""scripts/reproduce_zero_llm.py 结构契约（EMSE Open Science 复制包编排器）。

锁定零 LLM 复算链的命令集完整性与基本执行语义：
- L0 命令集覆盖论文主数字复算入口（统计扩展 / 口径矩阵 / 引用核验）；
- 每条命令为 (非空名, 非空 argv, 正 tail 行数) 结构；
- `_run` 以本解释器执行并捕获输出尾；
- `_CHECKSUM_DIRS` 为相对 experiments/results/ 的目录。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    path = REPO_ROOT / "scripts" / "reproduce_zero_llm.py"
    spec = importlib.util.spec_from_file_location("reproduce_zero_llm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def test_command_lists_well_formed(mod):
    """每条命令为 (非空名, 非空 argv 列表, 正 tail 行数)。"""
    for name, argv, tail in mod._L0_COMMANDS + mod._L1_COMMANDS:
        assert isinstance(name, str) and name.strip()
        assert isinstance(argv, list) and argv
        assert all(isinstance(a, str) and a for a in argv)
        assert isinstance(tail, int) and tail > 0


def test_l0_commands_cover_key_numbers(mod):
    """L0 命令集覆盖论文主数字复算入口（统计扩展 / 口径矩阵 / 引用核验）。"""
    joined = " ".join(a for _, argv, _ in mod._L0_COMMANDS for a in argv)
    assert "emse_stats_extensions" in joined
    assert "emse_stats_report" in joined
    assert "check_citations.py" in joined
    assert "mutation-correlation" in joined


def test_checksum_dirs_are_relative(mod):
    """SHA256SUMS 校验目录为相对 experiments/results/ 的相对路径。"""
    assert mod._CHECKSUM_DIRS
    for d in mod._CHECKSUM_DIRS:
        assert d.startswith("experiments/results/")


def test_run_trivial_captures_tail(mod):
    """_run 以本解释器执行并捕获输出尾。"""
    rc, tail = mod._run(["-c", "print('repro-ok')"])
    assert rc == 0
    assert "repro-ok" in tail


def test_report_paths_inside_results(mod):
    """报告落盘路径位于 experiments/results/ 下。"""
    assert str(mod.REPORT_MD).startswith(str(REPO_ROOT / "experiments" / "results"))
    assert str(mod.REPORT_JSON).startswith(str(REPO_ROOT / "experiments" / "results"))
