#!/usr/bin/env python3
"""K 轮（2026-10-17）性能基准扩展的回归锁定：JSON 提取家族纳入 weekly 回归面。

锁定三件事：
1. `benchmark_json_extraction()` 的结构与迭代口径（4 条真实路径，键集合稳定）；
2. **基线漂移守卫**：基准新增/删除指标时 `docs/performance_baseline.json` 必须
   同步刷新——否则 weekly perf.yml 的"基线 N 项 / 当次 M 项"会静默漏比新指标
   （与项目"文档↔工件静默分裂"同一缺陷形态）；
3. `check_perf_regression.py` 的判定语义在"新类别 / 绝对下限 / strict"下不变
   （全部用合成数据构造，不依赖真实跑分与机器负载）。

背景：`extract_json_object/array` 是每条 LLM 响应都会走的最高频解析入口，
K 轮对围栏清洗做了内容保真修复（原始文本快路径），需要有性能回归面兜住
"为了正确性牺牲量级"的退化。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BENCH_PATH = _REPO_ROOT / "scripts" / "tools" / "performance_benchmark.py"
_GATE_PATH = _REPO_ROOT / "scripts" / "gates" / "check_perf_regression.py"
_BASELINE_PATH = _REPO_ROOT / "docs" / "performance_baseline.json"

_EXPECTED_JSON_METRICS = {"object_fenced_typical", "object_fenced_large", "object_truncated_repair", "array_fenced"}
_EXPECTED_ITERATIONS = {
    "object_fenced_typical": 2000,
    "object_fenced_large": 500,
    "object_truncated_repair": 500,
    "array_fenced": 1000,
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bench = _load_module("_perf_benchmark_k", _BENCH_PATH)
gate = _load_module("_perf_gate_k", _GATE_PATH)


class TestJsonExtractionBenchmark:
    def test_metric_set_and_iterations_are_stable(self) -> None:
        results = bench.benchmark_json_extraction()
        assert set(results) == _EXPECTED_JSON_METRICS
        for name, row in results.items():
            assert row["iterations"] == _EXPECTED_ITERATIONS[name], name
            assert row["avg_ms"] > 0 and row["min_ms"] > 0 and row["max_ms"] >= row["avg_ms"], name

    def test_fenced_large_is_not_pathologically_slow(self) -> None:
        """2KB 围栏 JSON 单次解析应远低于 5ms（数量级守卫，防算法级退化）。"""
        results = bench.benchmark_json_extraction()
        assert results["object_fenced_large"]["avg_ms"] < 5.0

    def test_benchmark_is_repeatable_shape(self) -> None:
        """连续两次跑分键集合/迭代数一致（基准本身不得有一次性状态）。"""
        first = bench.benchmark_json_extraction()
        second = bench.benchmark_json_extraction()
        assert {k: v["iterations"] for k, v in first.items()} == {k: v["iterations"] for k, v in second.items()}


class TestBaselineDriftGuard:
    def test_baseline_covers_every_benchmark_metric(self) -> None:
        """基准指标集合 ⊆ 基线指标集合：新增指标必须刷新基线，不得静默漏比。"""
        baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert "json_extraction" in baseline, "基线缺少 json_extraction 类别：先跑基准再刷新基线"
        assert set(baseline["json_extraction"]) >= _EXPECTED_JSON_METRICS

    def test_gate_iter_metrics_sees_new_category(self) -> None:
        baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        keys = {f"{category}/{metric}" for category, metric, _ in gate._iter_metrics(baseline)}
        assert {f"json_extraction/{name}" for name in _EXPECTED_JSON_METRICS} <= keys


class TestGateSemanticsWithSyntheticData:
    """合成数据锁判定语义：不依赖真实跑分，因此不受机器负载影响。"""

    @staticmethod
    def _write(tmp_path: Path, name: str, data: dict) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def _run_gate(monkeypatch, baseline: Path, current: Path, *extra: str) -> int:
        argv = ["check_perf_regression.py", "--baseline", str(baseline), "--current", str(current), *extra]
        monkeypatch.setattr(sys, "argv", argv)
        return gate.main()

    def test_below_abs_floor_never_warns(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """两条指标都在 0.05ms 绝对下限之下：定时器噪声不得触发告警。"""
        base = self._write(tmp_path, "base.json", {"json_extraction": {"a": {"avg_ms": 0.001}}})
        cur = self._write(tmp_path, "cur.json", {"json_extraction": {"a": {"avg_ms": 0.02}}})
        assert self._run_gate(monkeypatch, base, cur) == 0
        assert "无性能劣化告警" in capsys.readouterr().out

    def test_clear_regression_warns_but_non_blocking(self, tmp_path: Path, monkeypatch, capsys) -> None:
        base = self._write(tmp_path, "base.json", {"json_extraction": {"a": {"avg_ms": 0.001}}})
        cur = self._write(tmp_path, "cur.json", {"json_extraction": {"a": {"avg_ms": 5.0}}})
        assert self._run_gate(monkeypatch, base, cur) == 0, "默认 non-blocking：有告警也返回 0"
        assert "[warn]" in capsys.readouterr().out

    def test_strict_turns_warning_into_failure(self, tmp_path: Path, monkeypatch) -> None:
        base = self._write(tmp_path, "base.json", {"json_extraction": {"a": {"avg_ms": 0.001}}})
        cur = self._write(tmp_path, "cur.json", {"json_extraction": {"a": {"avg_ms": 5.0}}})
        assert self._run_gate(monkeypatch, base, cur, "--strict") == 1

    def test_metric_missing_in_current_is_reported_not_silent(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """当次缺基线指标 → 记为告警（脚本输出结构变更必须可见），不得静默通过。"""
        base = self._write(tmp_path, "base.json", {"json_extraction": {"a": {"avg_ms": 0.001}}})
        cur = self._write(tmp_path, "cur.json", {"json_extraction": {"b": {"avg_ms": 0.001}}})
        assert self._run_gate(monkeypatch, base, cur) == 0
        out = capsys.readouterr().out
        assert "缺失" in out

    def test_empty_structure_returns_two(self, tmp_path: Path, monkeypatch) -> None:
        """基线/当次均无可比指标 → 结构不兼容退出码 2（快速失败，不静默判绿）。"""
        base = self._write(tmp_path, "base.json", {"_meta": {}})
        cur = self._write(tmp_path, "cur.json", {"_meta": {}})
        assert self._run_gate(monkeypatch, base, cur) == 2
