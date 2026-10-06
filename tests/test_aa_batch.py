"""AA 批次（2026-10-06 代码优化落地）回归测试。

覆盖三项优化（对应 2026-10-06 系统性审查报告 R-P0-3 残余 / R-P0-4a / R-P2-5）：
- AA1：logic 档预设补 DETECTION_FIRST_ENABLE（ADR-0015 W3 行为层核心；
  档位定义于 O1、早于 W3 落地而漏配）；
- AA2：SyntheticDataset.max_pattern_repeat 同池模板重复上限（opt-in，
  None=历史口径，rng 消费序列逐位不变）；
- AA3：README CI 矩阵漂移守卫（README(.en) ↔ BASELINE.yaml python_ci_matrix
  一致性，防"文档矩阵 ≠ CI 实跑矩阵"再漂移）。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import os as _os
import re
from collections import Counter
from pathlib import Path
from typing import ClassVar

import pytest

from config import _PROFILE_PRESETS, _apply_profile_presets
from src.datasets.synthetic_dataset import BUG_PATTERNS, SyntheticDataset

_ROOT = Path(__file__).resolve().parents[1]


# ─── AA1：logic 档注入 DETECTION_FIRST_ENABLE ────────────────────────────────


class TestLogicProfileDetectionFirst:
    """logic 档 = scientific 超集 + 逻辑链强化 + 检出优先协议（AA 补齐）。

    setdefault 绕过 monkeypatch 追踪——清理列表动态取自 logic 档全部键
    （静态枚举会在档位扩键时漏清理，泄漏的开关会污染同 worker 后续测试：
    本批次首版即因此误伤 test_patch_rollback / test_planner 共 5 用例）。
    """

    _INJECTED: ClassVar[list[str]] = sorted(_PROFILE_PRESETS["logic"])

    @pytest.fixture(autouse=True)
    def _cleanup_env(self):
        # 先清场再断言：xdist 同 worker 先行测试可能残留该键（全局"不存在"
        # 断言必须建立在测试自建的干净基线上，而非会话继承状态）。
        saved = {k: _os.environ.get(k) for k in self._INJECTED}
        for k in self._INJECTED:
            _os.environ.pop(k, None)
        yield
        for k, v in saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    def test_logic_preset_includes_detection_first(self, monkeypatch):
        assert _PROFILE_PRESETS["logic"]["DETECTION_FIRST_ENABLE"] == "true"
        monkeypatch.setenv("AITESTER_PROFILE", "logic")
        assert _apply_profile_presets() == "logic"
        assert _os.environ.get("DETECTION_FIRST_ENABLE") == "true"

    def test_explicit_env_wins(self, monkeypatch):
        monkeypatch.setenv("AITESTER_PROFILE", "logic")
        monkeypatch.setenv("DETECTION_FIRST_ENABLE", "false")
        _apply_profile_presets()
        assert _os.environ.get("DETECTION_FIRST_ENABLE") == "false"

    def test_fast_profile_unchanged(self, monkeypatch):
        monkeypatch.setenv("AITESTER_PROFILE", "fast")
        _apply_profile_presets()
        assert _os.environ.get("DETECTION_FIRST_ENABLE") is None


# ─── AA2：SyntheticDataset.max_pattern_repeat ────────────────────────────────


def _sig(ds: SyntheticDataset) -> list[tuple[str, str, str]]:
    """任务签名：(task_id, pattern_name, instance_code) 序列（判等口径）。"""
    return [(t.task_id, t.metadata["pattern_name"], t.instance_code) for t in ds.tasks]


class TestSyntheticPatternRepeatCap:
    """max_pattern_repeat 采样上限（opt-in；None=历史口径 rng 序列不变）。"""

    def test_default_none_is_historical(self):
        ds = SyntheticDataset(task_count=30, seed=42, difficulty="level1")
        assert ds.size == 30
        assert ds._max_pattern_repeat is None

    def test_large_cap_equivalent_to_default(self):
        """上限大于任何模板可达次数时，采样序列与历史口径逐位一致。"""
        base = SyntheticDataset(task_count=40, seed=42, difficulty="level1")
        capped = SyntheticDataset(task_count=40, seed=42, difficulty="level1", max_pattern_repeat=999)
        assert _sig(base) == _sig(capped)

    def test_cap_one_pool_sized_run_all_distinct(self):
        """cap=1 且 task_count=池规模：首个轮转周期内每模板恰出现一次。"""
        pool_size = len(BUG_PATTERNS)
        ds = SyntheticDataset(task_count=pool_size, seed=42, difficulty="level1", max_pattern_repeat=1)
        names = [t.metadata["pattern_name"] for t in ds.tasks]
        assert len(names) == pool_size
        assert len(set(names)) == pool_size

    def test_cap_one_two_cycles_each_twice(self):
        """cap=1 且 task_count=2×池规模：全池达上限清零轮转后每模板恰两次。"""
        pool_size = len(BUG_PATTERNS)
        ds = SyntheticDataset(task_count=pool_size * 2, seed=42, difficulty="level1", max_pattern_repeat=1)
        counts = Counter(t.metadata["pattern_name"] for t in ds.tasks)
        assert set(counts.values()) == {2}

    def test_invalid_cap_falls_back_to_none(self):
        """cap<1 无效：告警后回退历史口径（采样序列与 None 逐位一致）。"""
        base = SyntheticDataset(task_count=25, seed=42, difficulty="level1")
        bad = SyntheticDataset(task_count=25, seed=42, difficulty="level1", max_pattern_repeat=0)
        assert bad._max_pattern_repeat is None
        assert _sig(base) == _sig(bad)

    def test_cap_two_bounds_repeat_within_cycle(self):
        """cap=2 且 task_count=池规模：任一模板至多出现 2 次。"""
        pool_size = len(BUG_PATTERNS)
        ds = SyntheticDataset(task_count=pool_size, seed=123, difficulty="level1", max_pattern_repeat=2)
        counts = Counter(t.metadata["pattern_name"] for t in ds.tasks)
        assert max(counts.values()) <= 2
        assert sum(counts.values()) == pool_size

    def test_reproducible_with_cap(self):
        a = SyntheticDataset(task_count=35, seed=7, difficulty="level1", max_pattern_repeat=2)
        b = SyntheticDataset(task_count=35, seed=7, difficulty="level1", max_pattern_repeat=2)
        assert _sig(a) == _sig(b)


# ─── AA3：README CI 矩阵 ↔ BASELINE.yaml 一致性守卫 ─────────────────────────


class TestCIMatrixDocGuard:
    """README 的 CI 矩阵表述必须与 BASELINE.yaml python_ci_matrix 一致。

    此前 README 写"3.12, 3.14"而 ci.yml 实跑 ['3.12', '3.13', '3.14']
    （BASELINE.yaml 为单一事实来源）——静态守卫防再漂移。
    """

    @staticmethod
    def _baseline_matrix() -> list[str]:
        text = (_ROOT / "BASELINE.yaml").read_text(encoding="utf-8")
        m = re.search(r"python_ci_matrix:\s*\[([^\]]+)\]", text)
        assert m, "BASELINE.yaml 缺 python_ci_matrix 节"
        versions = re.findall(r"\d+\.\d+", m.group(1))
        assert versions, "python_ci_matrix 为空"
        return versions

    @pytest.mark.parametrize("readme_name", ["README.md", "README.en.md"])
    def test_readme_matrix_matches_baseline(self, readme_name: str):
        expected = " / ".join(self._baseline_matrix())
        readme = (_ROOT / readme_name).read_text(encoding="utf-8")
        assert expected in readme, f"{readme_name} CI 矩阵应包含 {expected!r}（与 BASELINE.yaml 一致）"
