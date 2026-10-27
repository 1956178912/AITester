"""EZ（2026-10-27）BASELINE 降级解析与 pre-commit 解释器选择回归锁。

缺陷族：`check_baseline.py` 在**缺 PyYAML** 时走最小行解析兜底，而该兜底把
**每个**非缩进行都当成节起点（`data[key] = {}`）——顶层标量
`last_verified: "2026-10-27"` 与 `error_categories: 18` 被读成空 dict，
结构校验因此**恒红 2 项**。

这条兜底只在「没有 PyYAML」时执行，而那正是 pre-commit 钩子的环境
（钩子用系统 `python3`，本机装的是不需要 yaml 的裸解释器）：实测 HEAD 上
`python3 scripts/gates/check_baseline.py` = rc=1、`.venv/bin/python3` = rc=0。
后果不是「少判一项」，而是**唯一的提交路径变成 `--no-verify`**——密钥泄漏 /
仓库卫生 / ruff 三道守卫一起失效。

锁定口径：
1. 顶层 `key: value` 是标量，`key:`（空值）才是节起点；
2. 兜底解析与 PyYAML 在**本门实际消费的键**上逐键一致（两个解析器不得分叉）；
3. 缺 PyYAML 时本门真实执行且 rc=0（不是靠环境碰巧有 yaml）；
4. 钩子必须优先选用仓库虚拟环境解释器（接线锁，防「兜底修好了、钩子仍走裸解释器」）。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "gates" / "check_baseline.py"
HOOK = ROOT / ".git-hooks" / "pre-commit.sh"
BASELINE = ROOT / "BASELINE.yaml"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_baseline_ez", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def test_top_level_scalars_are_not_sections(gate):
    text = (
        'version: "1"\n'
        'last_verified: "2026-10-27"   # EZ 轮\n'
        "error_categories: 18\n"
        "tests:\n"
        "  total_passed: 13430\n"
        "  total_failed: 0\n"
    )
    data = gate._parse_baseline_text(text)
    assert data["last_verified"] == "2026-10-27"
    assert data["error_categories"] == 18
    assert data["version"] == "1"
    assert data["tests"] == {"total_passed": 13430, "total_failed": 0}


def test_empty_value_opens_a_section(gate):
    """负向对照：`key:` 空值仍是节起点（不能因为上一个键是标量就把子行吞掉）。"""
    data = gate._parse_baseline_text("top: 1\nsec:\n  a: 2\n  b: 3\n")
    assert data["top"] == 1
    assert data["sec"] == {"a": 2, "b": 3}


def test_fallback_agrees_with_pyyaml_on_consumed_keys(gate):
    """两个解析器在本门**实际消费**的键上必须逐键一致（分叉即红）。

    兜底解析只保留节的**一级子键**（`coverage.core_modules` 之类的嵌套 map 会被
    拍平），这是它与 `check_structure()` 的约定边界：本门只读一级子键。
    """
    text = BASELINE.read_text(encoding="utf-8")
    fallback = gate._parse_baseline_text(text)
    parsed = yaml.safe_load(text)
    assert fallback["last_verified"] == parsed["last_verified"]
    assert fallback["error_categories"] == parsed["error_categories"]
    for section, fields in (
        ("tests", ("total_passed", "total_failed", "suite_seconds")),
        ("coverage", ("line_total_pct", "branch_total_pct")),
        ("static_checks", ("ruff_warnings", "mypy_errors")),
    ):
        for field in fields:
            assert fallback[section][field] == parsed[section][field], f"{section}.{field}"


def test_gate_passes_when_pyyaml_is_unavailable(tmp_path):
    """端到端：缺 PyYAML 时本门真实执行且 rc=0（HEAD 上此处为 rc=1 + 2 项 FAIL）。"""
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "yaml.py").write_text("raise ImportError('blocked for EZ test')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(blocker)}
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert "No module named 'yaml'" not in (proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "结构校验通过" in proc.stdout


def test_hook_prefers_repo_venv_interpreter():
    """接线锁：钩子必须先找 `.venv/bin/python3`，再回退系统解释器。"""
    text = HOOK.read_text(encoding="utf-8")
    assert ".venv/bin/python3" in text
    assert text.index(".venv/bin/python3") < text.index('PY="python3"')
    assert 'PY="${PYTHON:-}"' in text
