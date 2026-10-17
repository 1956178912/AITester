#!/usr/bin/env python3
"""A-06（2026-10-17 独立评审）：M1 判分 per-test 超时。

背景：QuixBugs 41 缺陷程序口径 4 个任务的缺陷实现本身不终止
（bitcount / sqrt / wrap / find_first_in_sorted）——历史判分（整套餐
120s 墙钟）下生成测试在 buggy 侧被整体击杀 → detection=None（fail-closed
正确但损失可判定样本）。修复：`_run_pytest_in_tmp` 支持 per-test 超时
（pytest-timeout `--timeout=N`，signal 方法可中断纯 Python 死循环），
由环境变量 M1_PER_TEST_TIMEOUT 控制（0/缺省 = 历史口径，零默认行为
变化；插件不可用时回退历史口径并告警）。

本文件锁定：
1. 开关解析（非正/非法 → 0）与插件可用性探测；
2. 机制：合成不终止目标上，历史口径 → None、per-test 口径 → 可判定；
3. 真实工件重放（零 LLM，skipif 数据缺失）：bitcount 由 None 转为
   F2P 可判定（buggy 红 ∧ fixed 绿）；
4. 重放工具 experiments/a06_per_test_timeout_replay.py 的 CLI 冒烟。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments._m1_metrics import (
    _PER_TEST_TIMEOUT_ENV,
    _pytest_timeout_plugin_available,
    _run_pytest_in_tmp,
    per_test_timeout_seconds,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_E4_BATCH = _REPO_ROOT / "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness/aitester.json"
_QUIXBUGS_DATA = _REPO_ROOT / "data/quixbugs/python_programs"

_NONTERMINATING_TARGET = """
def loopy(n):
    total = 0
    while n:
        n ^= n - 1  # 对任何 n 都不终止（bitcount 同型缺陷）
        total += 1
    return total
"""

_NONTERMINATING_TEST = """
from loopy import loopy


def test_loopy_returns_zero_for_zero():
    assert loopy(0) == 0


def test_loopy_hangs_for_positive():
    assert loopy(1) == 1
"""


class TestPerTestTimeoutConfig:
    def test_env_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_PER_TEST_TIMEOUT_ENV, raising=False)
        assert per_test_timeout_seconds() == 0
        monkeypatch.setenv(_PER_TEST_TIMEOUT_ENV, "3")
        assert per_test_timeout_seconds() == 3
        monkeypatch.setenv(_PER_TEST_TIMEOUT_ENV, "0")
        assert per_test_timeout_seconds() == 0
        monkeypatch.setenv(_PER_TEST_TIMEOUT_ENV, "abc")
        assert per_test_timeout_seconds() == 0
        monkeypatch.setenv(_PER_TEST_TIMEOUT_ENV, "-5")
        assert per_test_timeout_seconds() == 0

    def test_plugin_available_in_venv(self) -> None:
        """项目 dev 依赖含 pytest-timeout——探测必须为真（否则回退逻辑会静默降级）。"""
        assert _pytest_timeout_plugin_available() is True


class TestPerTestTimeoutMechanism:
    """合成不终止目标：历史口径 None、per-test 口径可判定。"""

    def test_historical_caliber_times_out_to_none(self) -> None:
        # 墙钟 6s：不终止测试拖垮整套餐 → None（历史口径行为锁定）
        res = _run_pytest_in_tmp(_NONTERMINATING_TEST, _NONTERMINATING_TARGET, "loopy", timeout=6, per_test_timeout=0)
        assert res is None

    def test_per_test_caliber_is_decidable(self) -> None:
        # per-test 2s：挂死测试被单独判失败（rc=1），其余测试完赛
        res = _run_pytest_in_tmp(_NONTERMINATING_TEST, _NONTERMINATING_TARGET, "loopy", timeout=30, per_test_timeout=2)
        assert res is not None
        rc, stdout, _stderr = res
        assert rc == 1
        assert "Timeout" in stdout or "timeout" in stdout

    def test_per_test_caliber_fixed_side_green(self) -> None:
        # 修复侧（真正数位的实现）两条测试均过 → F2P 的 fixed 段成立
        fixed = """
def loopy(n):
    return bin(n).count("1") if n >= 0 else 0
"""
        res = _run_pytest_in_tmp(_NONTERMINATING_TEST, fixed, "loopy", timeout=30, per_test_timeout=2)
        assert res is not None and res[0] == 0

    def test_env_switch_wired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """per_test_timeout 缺省时读环境变量（接线锁定）。"""
        monkeypatch.setenv(_PER_TEST_TIMEOUT_ENV, "2")
        res = _run_pytest_in_tmp(_NONTERMINATING_TEST, _NONTERMINATING_TARGET, "loopy", timeout=30)
        assert res is not None and res[0] == 1


@pytest.mark.skipif(not _E4_BATCH.exists(), reason="E4 FIXED harness 批次工件缺失")
@pytest.mark.skipif(not _QUIXBUGS_DATA.exists(), reason="vendored QuixBugs 数据缺失（data/ gitignore）")
class TestNonterminatingQuixbugsReplay:
    """真实工件零 LLM 重放：bitcount 由 None 转为可判定（A-06 核心证据）。"""

    def test_bitcount_none_to_decidable(self) -> None:
        data = json.loads(_E4_BATCH.read_text(encoding="utf-8"))
        rows = {str(r.get("task_id")): r for r in data["results"]["aitester"]["details"]}
        row = rows["quixbugs__bitcount"]
        assert row.get("detection_rate") is None  # 历史口径：None
        md = row["task_metadata"]
        gen = row["generated_test"]
        buggy = (_QUIXBUGS_DATA / "bitcount.py").read_text(encoding="utf-8")
        fixed = md["fixed"]

        res_b = _run_pytest_in_tmp(gen, buggy, "bitcount", timeout=90, task_metadata=md, per_test_timeout=2)
        res_f = _run_pytest_in_tmp(gen, fixed, "bitcount", timeout=90, task_metadata=md, per_test_timeout=2)
        assert res_b is not None, "per-test 口径下 buggy 侧应完赛（挂死测试被单独击杀）"
        assert res_f is not None and res_f[0] == 0, "fixed 侧应全过"
        assert res_b[0] == 1, "buggy 侧应为红（挂死测试判失败）"
        # 即 F2P 反事实判定 = 1.0（检出）

    def test_replay_tool_cli_smoke(self, tmp_path: Path) -> None:
        """重放工具 CLI 冒烟（单任务，输出 JSON 结构完整）。"""
        out = tmp_path / "replay.json"
        proc = subprocess.run(
            [
                sys.executable,
                "experiments/a06_per_test_timeout_replay.py",
                "--batch",
                str(_E4_BATCH),
                "--arm",
                "aitester",
                "--per-test",
                "2",
                "--wall",
                "60",
                "--tasks",
                "find_first_in_sorted",
                "--out",
                str(out),
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr[-500:]
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["per_test_timeout_s"] == 2
        assert len(payload["results"]) == 1
        assert payload["results"][0]["counterfactual_detection"] in (0.0, 1.0)
